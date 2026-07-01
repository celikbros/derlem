package httpapi

import (
	"net/http"
	"slices"
)

const (
	roleAdmin          = "admin"
	roleDataManager    = "data_manager"
	roleEditor         = "editor"
	roleModerator      = "moderator"
	roleExpertReviewer = "expert_reviewer"
	roleContributor    = "contributor"
	roleConsumerTeam   = "consumer_team"
)

var (
	applicationRoles = []string{
		roleAdmin,
		roleDataManager,
		roleEditor,
		roleModerator,
		roleExpertReviewer,
		roleContributor,
		roleConsumerTeam,
	}
	sourceWorkspaceRoles = []string{
		roleAdmin,
		roleDataManager,
		roleEditor,
		roleModerator,
		roleExpertReviewer,
	}
	sourceManagerRoles  = []string{roleAdmin, roleDataManager}
	sourceEditorRoles   = []string{roleAdmin, roleDataManager, roleEditor}
	documentEditorRoles = []string{roleAdmin, roleEditor}
	reviewerRoles       = []string{roleAdmin, roleModerator, roleExpertReviewer}
	jobReaderRoles      = []string{roleAdmin, roleDataManager}
	releaseReaderRoles  = []string{roleAdmin, roleDataManager, roleConsumerTeam}
)

type protectedRoute struct {
	pattern string
	roles   []string
	handler http.HandlerFunc
}

// protectedRoutes is the fail-closed API policy: every data route must declare
// at least one role before it can be registered.
func protectedRoutes(s *Server) []protectedRoute {
	return []protectedRoute{
		{"POST /api/v1/auth/logout", applicationRoles, s.logout},
		{"POST /api/v1/auth/logout-all", applicationRoles, s.logoutAll},
		{"GET /api/v1/sources", sourceWorkspaceRoles, s.listSources},
		{"POST /api/v1/sources", sourceManagerRoles, s.createSource},
		{"GET /api/v1/sources/{id}", sourceWorkspaceRoles, s.getSource},
		{"PATCH /api/v1/sources/{id}", sourceEditorRoles, s.updateSource},
		{"POST /api/v1/sources/{id}/ingest", sourceManagerRoles, s.queueSourceIngest},
		{"POST /api/v1/sources/{id}/upload", sourceManagerRoles, s.uploadSourceFile},
		{"GET /api/v1/sources/{id}/reviews", sourceWorkspaceRoles, s.listSourceReviews},
		{"POST /api/v1/sources/{id}/reviews", reviewerRoles, s.reviewSource},
		{"GET /api/v1/sources/{id}/pii-scans", sourceWorkspaceRoles, s.listSourcePIIScans},
		{"GET /api/v1/sources/{id}/documents", sourceWorkspaceRoles, s.listSourceDocuments},
		{"GET /api/v1/sources/{id}/document-quality-summary", sourceWorkspaceRoles, s.getDocumentQualitySummary},
		{"GET /api/v1/sources/{id}/document-sample-generations", sourceWorkspaceRoles, s.listDocumentSampleGenerations},
		{"POST /api/v1/sources/{id}/documents/resample", []string{roleAdmin}, s.queueDocumentResample},
		{"POST /api/v1/sources/{id}/documents/bulk-reviews", reviewerRoles, s.bulkReviewDocuments},
		{"GET /api/v1/documents/{id}", sourceWorkspaceRoles, s.getDocument},
		{"PATCH /api/v1/documents/{id}", documentEditorRoles, s.updateDocument},
		{"GET /api/v1/documents/{id}/reviews", sourceWorkspaceRoles, s.listDocumentReviews},
		{"POST /api/v1/documents/{id}/reviews", reviewerRoles, s.reviewDocument},
		{"GET /api/v1/jobs", jobReaderRoles, s.listJobs},
		{"GET /api/v1/releases", releaseReaderRoles, s.listReleases},
		{"POST /api/v1/releases", sourceManagerRoles, s.createRelease},
		{"GET /api/v1/releases/{id}", releaseReaderRoles, s.getRelease},
		{"POST /api/v1/releases/{id}/freeze", []string{roleAdmin}, s.freezeRelease},
		{"POST /api/v1/releases/{id}/exports", sourceManagerRoles, s.createReleaseExport},
		{"GET /api/v1/releases/{id}/manifest", releaseReaderRoles, s.downloadReleaseManifest},
		{"GET /api/v1/releases/{id}/exports/{format}/artifact", releaseReaderRoles, s.downloadReleaseExport},
		{"GET /api/v1/releases/{id}/exports/{format}/manifest", releaseReaderRoles, s.downloadReleaseExportManifest},
		{"GET /api/v1/releases/{id}/sources/{source_id}/artifact", releaseReaderRoles, s.downloadReleaseSource},
		{"GET /api/v1/similarity-calibrations", reviewerRoles, s.listSimilarityCalibrationRuns},
		{"GET /api/v1/similarity-calibrations/{id}/pairs", reviewerRoles, s.listSimilarityReviewPairs},
		{"GET /api/v1/similarity-pairs/{id}", reviewerRoles, s.getSimilarityReviewPair},
		{"POST /api/v1/similarity-pairs/{id}/reviews", reviewerRoles, s.reviewSimilarityPair},
	}
}

func hasAnyRole(assigned, allowed []string) bool {
	for _, role := range assigned {
		if slices.Contains(allowed, role) {
			return true
		}
	}
	return false
}

func canReadDraftReleases(roles []string) bool {
	return hasAnyRole(roles, sourceManagerRoles)
}
