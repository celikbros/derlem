"use client";

import { Gauge } from "lucide-react";

import { humanRejectRate, intervalLabel, juryLabel, rateLabel, readQualityNumbers } from "@/lib/quality-numbers";
import type { QualityNumbers, QualityRate } from "@/lib/quality-numbers";
import type { Source } from "@/lib/types";

type Tone = "neutral" | "good" | "watch" | "risk";

function toneFor(rate: Partial<QualityRate> | null | undefined, watchAt: number, riskAt: number): Tone {
  if (!rate || rate.rate === null || rate.rate === undefined || !rate.n) return "neutral";
  if (rate.rate >= riskAt) return "risk";
  if (rate.rate >= watchAt) return "watch";
  return "good";
}

function QualityMetric({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: Tone }) {
  return (
    <div className={`corpus-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small className="quality-interval">{detail}</small>}
    </div>
  );
}

// Kaynak kartı: dört sayı (TASK-047). Sayılar örneklem üzerindedir; aralık Wilson %95.
export function QualityNumbersSection({ source }: { source: Source }) {
  const numbers = readQualityNumbers(source);
  const human = humanRejectRate(source);
  return (
    <section className="inspector-section" data-testid="source-quality-numbers">
      <h3><Gauge size={16} /> Kalite sayıları</h3>
      {!numbers && !human ? (
        <p className="muted-copy">Bu kaynak için hakem örneklemesi henüz koşmadı (iş: <code>jury_sample</code>).</p>
      ) : (
        <>
          <div className="corpus-summary-grid">
            <QualityMetric label="PII isabeti" value={rateLabel(numbers?.pii)} detail={intervalLabel(numbers?.pii)} tone={toneFor(numbers?.pii, 0.01, 0.05)} />
            <QualityMetric label="Kural atma" value={rateLabel(numbers?.rule)} detail={numbers ? `${numbers.rule.policy} · ${intervalLabel(numbers.rule)}` : ""} tone={toneFor(numbers?.rule, 0.05, 0.2)} />
            <QualityMetric label="Hakem çöp" value={juryLabel(numbers)} detail={numbers?.jury.status === "judged" ? intervalLabel(numbers.jury) : ""} tone={numbers?.jury.status === "judged" ? toneFor(numbers.jury, 0.2, 0.4) : "neutral"} />
            <QualityMetric label="İnsan ret" value={human ? rateLabel(human) : "İncelenmedi"} detail={intervalLabel(human)} tone={toneFor(human, 0.05, 0.1)} />
          </div>
          {numbers && <QualityProvenance numbers={numbers} />}
        </>
      )}
    </section>
  );
}

function QualityProvenance({ numbers }: { numbers: QualityNumbers }) {
  const retest = numbers.jury.retest;
  return (
    <details className="evidence-technical">
      <summary>Ölçüm kaydı</summary>
      <dl className="quality-provenance">
        <dt>Örneklem</dt>
        <dd>n={numbers.sample.n} / {numbers.sample.population_documents.toLocaleString("tr-TR")} belge · tohum {numbers.sample.seed}</dd>
        <dt>Hakem</dt>
        <dd><code>{numbers.judge_id ?? "—"}</code>{numbers.judge_model ? ` · ${numbers.judge_model}` : ""}</dd>
        {retest && (
          <>
            <dt>Test-tekrar</dt>
            <dd>uyum {rateLabel({ rate: retest.agreement_binary, n: retest.n })} · kappa {retest.kappa_binary === null ? "—" : retest.kappa_binary.toFixed(2)}</dd>
          </>
        )}
        <dt>Koşu</dt>
        <dd><code>{numbers.run_id}</code></dd>
        {numbers.decisions && (
          <>
            <dt>Kararlar</dt>
            <dd>{numbers.decisions.rows} satır · <code>{numbers.decisions.sha256.slice(0, 12)}…</code></dd>
          </>
        )}
        {numbers.cost && (
          <>
            <dt>Maliyet</dt>
            <dd>{numbers.cost.calls} çağrı{numbers.cost.estimated_usd !== null ? ` · ~$${numbers.cost.estimated_usd}` : ""} ({numbers.cost.price_table})</dd>
          </>
        )}
        <dt>Hesaplandı</dt>
        <dd>{new Date(numbers.computed_at).toLocaleString("tr-TR")}</dd>
      </dl>
    </details>
  );
}

// Karşılaştırma görünümü: bütün pretrain kaynakları yan yana.
export function QualityComparison({ sources, onSelect }: { sources: Source[]; onSelect: (source: Source) => void }) {
  const pretrain = sources.filter((source) => source.content_purpose === "pretrain");
  if (pretrain.length === 0) return null;
  const measured = pretrain.filter((source) => readQualityNumbers(source) !== null).length;
  return (
    <details className="quality-comparison" data-testid="quality-comparison">
      <summary>Kalite karşılaştırması · {measured}/{pretrain.length} pretrain kaynağı ölçüldü</summary>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Kaynak</th>
              <th>PII isabeti</th>
              <th>Kural atma</th>
              <th>Hakem çöp (%95)</th>
              <th>İnsan ret</th>
            </tr>
          </thead>
          <tbody>
            {pretrain.map((source) => {
              const numbers = readQualityNumbers(source);
              const human = humanRejectRate(source);
              return (
                <tr key={source.id}>
                  <td>
                    <button className="source-link" type="button" onClick={() => onSelect(source)}>
                      <strong>{source.name}</strong>
                      <span>{numbers ? `n=${numbers.sample.n}` : "ölçülmedi"}</span>
                    </button>
                  </td>
                  <td>{rateLabel(numbers?.pii)}</td>
                  <td>{rateLabel(numbers?.rule)}</td>
                  <td>
                    {juryLabel(numbers)}
                    {numbers?.jury.status === "judged" && <small className="quality-interval"> {intervalLabel(numbers.jury)}</small>}
                  </td>
                  <td>{human ? rateLabel(human) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}
