import catalog from "./contribution-task-types.json";

// Katkı görev tipleri Go kayıt defterinden üretilir (internal/domain/contribution.go
// → contribution-task-types.json); web'de elle liste tutulmaz. Go'da bir tip değişip
// JSON yenilenmezse TestContributionCatalogMatchesWebFixture kırmızı olur.

export type ContributionPayloadFieldSpec = {
  key: string;
  label: string;
  required: boolean;
  max_chars: number;
};

export type ContributionTaskTypeSpec = {
  name: string;
  label: string;
  content_purpose: string;
  prompt_required: boolean;
  prompt_forbidden: boolean;
  prompt_label: string;
  body_label: string;
  payload: ContributionPayloadFieldSpec[];
  /** Değeri metinden farklı olmak zorunda olan payload anahtarı (boşsa yok). */
  distinct_from_body: string;
};

export type ContributionDataOriginSpec = {
  value: string;
  label: string;
  requires_model_id: boolean;
};

export const contributionTaskTypes: ContributionTaskTypeSpec[] = catalog.task_types;
export const contributionDataOrigins: ContributionDataOriginSpec[] = catalog.data_origins;

export function taskTypeSpec(name: string): ContributionTaskTypeSpec | undefined {
  return contributionTaskTypes.find((spec) => spec.name === name);
}

export function taskTypeLabel(name: string): string {
  return taskTypeSpec(name)?.label ?? name;
}

export function dataOriginSpec(value: string): ContributionDataOriginSpec | undefined {
  return contributionDataOrigins.find((origin) => origin.value === value);
}
