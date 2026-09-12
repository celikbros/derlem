-- PII tarayicisi yalniz Turkce'ye ozgu desenleri (TCKN, TR IBAN, TR telefon)
-- tanir. Desteklemedigi dildeki kaynaga "clear" yazmak, bakilamamis veriye hak
-- edilmemis bir temiz muhru basmakti ve freeze bu muhru kabul ediyordu.
--
-- Yeni durum: dile ozel dedektorler bu kaynagin dilinde uygulanamadi. Dilden
-- bagimsiz desenler (e-posta, kart) yine calisir ve bulgu varsa kaynak flagged
-- olur. Freeze kapilari 'clear' disindaki her degeri zaten reddettigi icin yeni
-- durum kapilara dokunmadan freeze'i bloke eder.

ALTER TABLE sources DROP CONSTRAINT sources_pii_status_check;
ALTER TABLE sources ADD CONSTRAINT sources_pii_status_check
    CHECK (pii_status IN ('not_scanned', 'clear', 'flagged', 'quarantined', 'not_evaluated'));

ALTER TABLE pii_scans DROP CONSTRAINT pii_scans_status_check;
ALTER TABLE pii_scans ADD CONSTRAINT pii_scans_status_check
    CHECK (status IN ('clear', 'flagged', 'failed', 'not_evaluated'));
