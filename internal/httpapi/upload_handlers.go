package httpapi

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"
	"unicode"

	"github.com/celikbros/derlem/internal/repository"
)

const multipartOverheadAllowance = int64(10 * 1024 * 1024)

func (s *Server) uploadSourceFile(w http.ResponseWriter, r *http.Request) {
	controller := http.NewResponseController(w)
	_ = controller.SetReadDeadline(time.Time{})
	_ = controller.SetWriteDeadline(time.Time{})
	r.Body = http.MaxBytesReader(w, r.Body, s.maxUploadBytes+multipartOverheadAllowance)

	reader, err := r.MultipartReader()
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_multipart", "Dosya yükleme isteği multipart/form-data olmalıdır.")
		return
	}

	var stagedPath, originalFilename string
	var byteSize int64
	for {
		part, err := reader.NextPart()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			writeUploadReadError(w, err)
			return
		}
		if part.FormName() != "file" || part.FileName() == "" {
			part.Close()
			continue
		}
		if stagedPath != "" {
			part.Close()
			os.Remove(stagedPath)
			writeError(w, http.StatusBadRequest, "multiple_files", "Her istekte yalnızca bir dosya yüklenebilir.")
			return
		}

		originalFilename = sanitizeUploadFilename(part.FileName())
		temp, err := os.CreateTemp(s.stagingRoot, "upload-*.part")
		if err != nil {
			part.Close()
			s.logger.Error("create staging file failed", "error", err)
			writeError(w, http.StatusInternalServerError, "staging_unavailable", "Yükleme alanı hazırlanamadı.")
			return
		}
		absolutePath, err := filepath.Abs(temp.Name())
		if err != nil {
			temp.Close()
			part.Close()
			os.Remove(temp.Name())
			writeError(w, http.StatusInternalServerError, "staging_unavailable", "Yükleme alanı çözümlenemedi.")
			return
		}
		stagedPath = absolutePath
		byteSize, err = io.CopyBuffer(temp, io.LimitReader(part, s.maxUploadBytes+1), make([]byte, 1024*1024))
		part.Close()
		if syncErr := temp.Sync(); err == nil {
			err = syncErr
		}
		if closeErr := temp.Close(); err == nil {
			err = closeErr
		}
		if err != nil {
			os.Remove(stagedPath)
			writeUploadReadError(w, err)
			return
		}
		if byteSize > s.maxUploadBytes {
			os.Remove(stagedPath)
			writeError(w, http.StatusRequestEntityTooLarge, "file_too_large", fmt.Sprintf("Dosya en fazla %d bayt olabilir.", s.maxUploadBytes))
			return
		}
	}

	if stagedPath == "" {
		writeError(w, http.StatusBadRequest, "file_required", "Yüklenecek dosya zorunludur.")
		return
	}

	principal, _ := principalFrom(r.Context())
	jobID, err := s.sources.QueueStagedIngest(
		r.Context(), r.PathValue("id"), stagedPath, originalFilename, byteSize, principal.Subject,
	)
	if err != nil {
		os.Remove(stagedPath)
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
			return
		}
		if errors.Is(err, repository.ErrConflict) {
			writeError(w, http.StatusConflict, "ingest_conflict", "Kaynak daha önce içe alınmış veya aktif bir içe aktarma işi var.")
			return
		}
		s.logger.Error("queue staged ingest failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Dosya içe aktarma kuyruğuna alınamadı.")
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"job_id": jobID, "status": "queued", "filename": originalFilename, "uploaded_bytes": byteSize,
	})
}

func sanitizeUploadFilename(value string) string {
	filename := path.Base(strings.ReplaceAll(strings.TrimSpace(value), "\\", "/"))
	filename = strings.Map(func(character rune) rune {
		if unicode.IsControl(character) {
			return -1
		}
		return character
	}, filename)
	if filename == "" || filename == "." {
		return "upload.bin"
	}
	if len(filename) > 240 {
		filename = filename[:240]
	}
	return filename
}

func writeUploadReadError(w http.ResponseWriter, err error) {
	var maxBytesError *http.MaxBytesError
	if errors.As(err, &maxBytesError) {
		writeError(w, http.StatusRequestEntityTooLarge, "file_too_large", "Dosya yükleme sınırını aşıyor.")
		return
	}
	writeError(w, http.StatusBadRequest, "upload_interrupted", "Dosya yükleme tamamlanamadı.")
}
