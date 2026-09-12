package httpapi

import (
	"errors"
	"io"
	"net/http"
	"time"
)

const (
	// Indirme govdesi bu boyutta parcalar halinde yazilir.
	downloadCopyBuffer = 1024 * 1024
	// Her bu kadar bayt yazildiktan sonra yazma suresi tazelenir.
	downloadDeadlineStep = int64(4 * 1024 * 1024)
	// Tazeleme araligi: istemci bu sure boyunca hic ilerlemezse baglanti duser.
	downloadStallTimeout = 2 * time.Minute
)

// copyDownloadBody, artifact govdesini yanita yazarken http.Server'in
// WriteTimeout suresini transfer ilerledikce tazeler. Boylece indirmenin toplam
// suresi sinirsizdir ama okumayi birakan istemci baglantiyi, soketi ve acik
// nesne dosyasini sonsuza kadar tutamaz.
//
// io.Copy/io.CopyBuffer bu is icin kullanilamaz: uygun oldugunda tum govdeyi tek
// bir io.ReaderFrom/io.WriterTo cagrisina (sendfile) devrederler; sure o tek
// cagri icinde tazelenemeyecegi icin buyuk indirmeler yine yarida kesilir.
func copyDownloadBody(w http.ResponseWriter, source io.Reader) (int64, error) {
	return copyRefreshingDeadline(w, source, downloadDeadlineStep, downloadStallTimeout)
}

func copyRefreshingDeadline(
	w http.ResponseWriter,
	source io.Reader,
	step int64,
	timeout time.Duration,
) (int64, error) {
	controller := http.NewResponseController(w)
	refresh := func() error {
		return controller.SetWriteDeadline(time.Now().Add(timeout))
	}

	// Sarmalanmis bir ResponseWriter sureyi desteklemiyorsa (orn. test
	// kaydedici) davranis bugunkunden kotu olmasin: duz kopyaya dus.
	refreshable := refresh() == nil

	buffer := make([]byte, downloadCopyBuffer)
	var total, sinceRefresh int64
	for {
		read, readErr := source.Read(buffer)
		if read > 0 {
			written, writeErr := w.Write(buffer[:read])
			total += int64(written)
			sinceRefresh += int64(written)
			if writeErr != nil {
				return total, writeErr
			}
			if refreshable && sinceRefresh >= step {
				sinceRefresh = 0
				if err := refresh(); err != nil {
					return total, err
				}
			}
		}
		if readErr != nil {
			if errors.Is(readErr, io.EOF) {
				return total, nil
			}
			return total, readErr
		}
	}
}
