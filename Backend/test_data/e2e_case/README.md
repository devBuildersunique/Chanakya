# Chanakya E2E Synthetic Test Case

Controlled synthetic evidence for testing the multi-format `POST /process` pipeline.

## Files
- report.txt - narrative text
- report.docx - narrative DOCX
- report.pdf - native-text PDF
- evidence.png - image for OCR
- cdr.csv - structured CDR
- transactions.xlsx - structured financial transfers
- criminal_history.json - structured criminal-history JSON
- expected_results.json - expected checks

## Expected narrative relations
- Rahul Kumar -> MET -> Ahmed Khan
- Rahul Kumar -> CONTACTED -> Ahmed Khan
- Rahul Kumar -> VISITED -> Kochi
- Ahmed Khan -> LOCATED_AT -> Malappuram
- Rahul Kumar -> 9123456789: explicit negation, so no USES_PHONE edge
- Suresh Menon -> Rahul Kumar: claim is explicitly unestablished/reverse, so no positive edge

## Expected structured relations
- Each CDR row maps caller -> CONTACTED -> receiver.
- Each transaction row maps sender_account -> TRANSFERRED_TO -> receiver_account.

All data is fictional and for software testing only.
