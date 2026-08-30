package httpapi

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
)

type apiError struct {
	Error errorBody `json:"error"`
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	if marker, ok := w.(interface{ markAuditFailure(string) }); ok {
		marker.markAuditFailure(code)
	}
	writeJSON(w, status, apiError{Error: errorBody{Code: code, Message: message}})
}

func decodeJSON(w http.ResponseWriter, r *http.Request, destination any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, 1024*1024)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", "İstek gövdesi geçerli JSON olmalıdır.")
		return false
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		writeError(w, http.StatusBadRequest, "invalid_json", "İstek yalnızca bir JSON nesnesi içermelidir.")
		return false
	}
	return true
}
