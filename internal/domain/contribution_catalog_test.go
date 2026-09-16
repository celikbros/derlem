package domain

import (
	"bytes"
	"encoding/json"
	"os"
	"strings"
	"testing"
)

// webCatalogFixture, web formunun tip listesini okuduğu dosya. Web ikinci bir
// liste tutmaz; Go kayıt defteri değişip bu dosya yenilenmezse bu test kırmızı
// olur. Yeniden üretmek için:
// DERLEM_UPDATE_GOLDEN=1 go test ./internal/domain/ -run TestContributionCatalogMatchesWebFixture
const webCatalogFixture = "../../web/lib/contribution-task-types.json"

func TestContributionCatalogMatchesWebFixture(t *testing.T) {
	built, err := json.MarshalIndent(ContributionTaskTypeCatalog(), "", "  ")
	if err != nil {
		t.Fatalf("marshal catalog: %v", err)
	}
	built = append(built, '\n')
	if os.Getenv("DERLEM_UPDATE_GOLDEN") == "1" {
		if err := os.WriteFile(webCatalogFixture, built, 0o644); err != nil {
			t.Fatalf("write web catalog: %v", err)
		}
	}
	fixture, err := os.ReadFile(webCatalogFixture)
	if err != nil {
		t.Fatalf("read web catalog (regenerate with DERLEM_UPDATE_GOLDEN=1): %v", err)
	}
	if !bytes.Equal(built, fixture) {
		t.Fatalf("contribution registry drifted from %s; regenerate it with DERLEM_UPDATE_GOLDEN=1.\nbuilt:\n%s", webCatalogFixture, built)
	}
}

func TestContributionCatalogCoversEveryRegistryEntry(t *testing.T) {
	catalog := ContributionTaskTypeCatalog()
	if len(catalog.TaskTypes) != len(ContributionTaskTypes) {
		t.Fatalf("catalog has %d task types, registry has %d", len(catalog.TaskTypes), len(ContributionTaskTypes))
	}
	orders := map[int]string{}
	for _, taskType := range catalog.TaskTypes {
		entry := ContributionTaskTypes[taskType.Name]
		if strings.TrimSpace(taskType.Label) == "" || strings.TrimSpace(taskType.BodyLabel) == "" {
			t.Errorf("%s: a form needs a type label and a body label", taskType.Name)
		}
		if !taskType.PromptForbidden && strings.TrimSpace(taskType.PromptLabel) == "" {
			t.Errorf("%s: a type that uses the prompt needs a prompt label", taskType.Name)
		}
		if taskType.PromptRequired && taskType.PromptForbidden {
			t.Errorf("%s: prompt cannot be both required and forbidden", taskType.Name)
		}
		if other, taken := orders[entry.DisplayOrder]; taken || entry.DisplayOrder <= 0 {
			t.Errorf("%s: display order %d must be positive and unique (also used by %q)", taskType.Name, entry.DisplayOrder, other)
		}
		orders[entry.DisplayOrder] = taskType.Name
		for _, field := range taskType.Payload {
			if strings.TrimSpace(field.Label) == "" || field.MaxChars <= 0 {
				t.Errorf("%s.payload.%s: a form field needs a label and a positive limit", taskType.Name, field.Key)
			}
		}
		if key := taskType.DistinctFromBody; key != "" {
			if _, declared := entry.Payload[key]; !declared {
				t.Errorf("%s: distinct_from_body %q is not a declared payload key", taskType.Name, key)
			}
		}
	}

	if len(catalog.DataOrigins) != len(ContributionDataOrigins) {
		t.Fatalf("origin options (%d) and validation vocabulary (%d) differ", len(catalog.DataOrigins), len(ContributionDataOrigins))
	}
	for _, option := range catalog.DataOrigins {
		if _, valid := ContributionDataOrigins[option.Value]; !valid {
			t.Errorf("origin option %q is not in the validation vocabulary", option.Value)
		}
		wantsModel := option.Value == "model" || option.Value == "hybrid"
		if option.RequiresModelID != wantsModel {
			t.Errorf("origin %q requires_model_id=%v, but validation requires a model id: %v", option.Value, option.RequiresModelID, wantsModel)
		}
		if strings.TrimSpace(option.Hint) == "" {
			t.Errorf("origin %q needs a help text", option.Value)
		}
	}
}

// Formun kendini anlatması kayıt defterine bağlıdır: yeni tip ya da alan
// açıklamasız eklenemez (TASK-009).
func TestContributionCatalogExplainsEveryField(t *testing.T) {
	for _, taskType := range ContributionTaskTypeCatalog().TaskTypes {
		if strings.TrimSpace(taskType.Description) == "" {
			t.Errorf("%s: a type needs a description shown under the type select", taskType.Name)
		}
		if !taskType.PromptForbidden && (strings.TrimSpace(taskType.PromptHint) == "" || strings.TrimSpace(taskType.PromptPlaceholder) == "") {
			t.Errorf("%s: a type that uses the prompt needs a prompt hint and an example", taskType.Name)
		}
		if strings.TrimSpace(taskType.BodyHint) == "" || strings.TrimSpace(taskType.BodyPlaceholder) == "" {
			t.Errorf("%s: the body needs a hint and an example", taskType.Name)
		}
		for _, field := range taskType.Payload {
			if strings.TrimSpace(field.Hint) == "" || strings.TrimSpace(field.Placeholder) == "" {
				t.Errorf("%s.payload.%s: a form field needs a hint and an example", taskType.Name, field.Key)
			}
			if strings.Contains(field.Label, "opsiyonel") {
				t.Errorf("%s.payload.%s: the form adds the optional marker; the label is also used in error messages", taskType.Name, field.Key)
			}
		}
		if origin := taskType.DefaultDataOrigin; origin != "" {
			if _, valid := ContributionDataOrigins[origin]; !valid {
				t.Errorf("%s: default origin %q is not in the validation vocabulary", taskType.Name, origin)
			}
		}
	}
}
