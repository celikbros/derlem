import catalog from "./contribution-task-types.json";

// Katkı görev tipleri Go kayıt defterinden üretilir (internal/domain/contribution.go
// → contribution-task-types.json); web'de elle liste tutulmaz. Go'da bir tip değişip
// JSON yenilenmezse TestContributionCatalogMatchesWebFixture kırmızı olur.

export type ContributionPayloadFieldSpec = {
  key: string;
  label: string;
  /** Yardım düğmesinin açtığı açıklama. */
  hint: string;
  /** Boş kutuda görünen örnek. */
  placeholder: string;
  required: boolean;
  max_chars: number;
};

export type ContributionTaskTypeSpec = {
  name: string;
  label: string;
  /** Tip seçiminin altında hep görünen açıklama. */
  description: string;
  content_purpose: string;
  prompt_required: boolean;
  prompt_forbidden: boolean;
  prompt_label: string;
  prompt_hint: string;
  prompt_placeholder: string;
  body_label: string;
  body_hint: string;
  body_placeholder: string;
  payload: ContributionPayloadFieldSpec[];
  /** Değeri metinden farklı olmak zorunda olan payload anahtarı (boşsa yok). */
  distinct_from_body: string;
  /** Bu tipte kökenin nasıl seçileceği (boş olabilir). */
  origin_hint: string;
  /** Tip seçilince önerilen köken (boşsa "human"). */
  default_data_origin: string;
};

export type ContributionDataOriginSpec = {
  value: string;
  label: string;
  requires_model_id: boolean;
  hint: string;
};

export const contributionTaskTypes: ContributionTaskTypeSpec[] = catalog.task_types;
export const contributionDataOrigins: ContributionDataOriginSpec[] = catalog.data_origins;
/** Köken sorusunun ne sorduğu: bilginin nereden öğrenildiği değil, kelimeleri kimin yazdığı. */
export const contributionDataOriginGuide: string = catalog.data_origin_guide;

export function taskTypeSpec(name: string): ContributionTaskTypeSpec | undefined {
  return contributionTaskTypes.find((spec) => spec.name === name);
}

export function taskTypeLabel(name: string): string {
  return taskTypeSpec(name)?.label ?? name;
}

export function dataOriginSpec(value: string): ContributionDataOriginSpec | undefined {
  return contributionDataOrigins.find((origin) => origin.value === value);
}
