# Checklist — 18/11/2026

Νεότερη επαλήθευση: [VERIFICATION.md](VERIFICATION.md). Τα runtime tests εκτελέστηκαν πλέον:60PASS και JavaScriptPASS. Οι παλαιότερες αναφορές αναμονής τεστ στον αρχικό πίνακα παρακάτω αντικαθίστανται από αυτή την καταγραφή· ο browser/production έλεγχος παραμένει εκκρεμής.

PASS σημαίνει επιβεβαίωση μόνο του αναφερόμενου scope. FIXED σημαίνει συγκεκριμένη αλλαγή κώδικα, όχι επιτυχές runtime test ούτε συμμόρφωση production. PARTIAL σημαίνει ανοικτή ουσιώδη εργασία. Καμία συνολική πιστοποίηση.

| Έλεγχος | Προτεραιότητα | Κατάσταση | Απόδειξη / επόμενο βήμα |
|---|---|---|---|
| Απογραφή λειτουργιών/δεδομένων | P1 | PARTIAL | DATA_INVENTORY.md, runtime/schema review· εξωτερικοί πάροχοι ανεπιβεβαίωτοι. |
| Στοιχεία υπευθύνου και τελική ενημέρωση | P0 | FAIL | Κενό controller/contact, προσχέδια. |
| Δημόσιες διαδρομές 7 νομικών/ενημερωτικών σελίδων | P1 | PARTIAL | app.py/templates/base.html· νέα URLs δεν εκτελέστηκαν σε τεστ/browser. |
| Αναγκαία cookies / απουσία analytics στο runtime | P2 | PASS | Στατικός έλεγχος script/templates· όχι ισχυρισμός για Render traffic. |
| Banner μη αναγκαίων cookies | P2 | NOT APPLICABLE | Δεν εντοπίστηκαν προαιρετικοί trackers. Νέος έλεγχος πριν analytics. |
| Αποθήκευση προτίμησης μόνο κατόπιν επιλογής | P2 | FIXED | script.js setFont(...,false) στην αρχική φόρτωση· νέο assertion εκκρεμεί. |
| Gunicorn αποφυγή bearer URL στα access logs | P1 | FIXED | Ρητό access_log_format method/status/bytes/duration. Δεν ελέγχθηκαν platform/error logs. |
| Προστασία απορρήτου/embedding/HTTPS headers | P1 | PARTIAL | no-referrer, DENY, nosniff, PermissionsPolicy, baseline CSP, HSTS production· νέα τεστ εκκρεμούν, strict script CSP λείπει. |
| Κωδικοί/CSRF/ανάκληση sessions | P1 | PASS | Προϋπάρχον auth.py και ιστορικοί έλεγχοι· δεν αποτελεί νέο penetration test. |
| SameSite/HttpOnly/Secure | P1 | PARTIAL | Ρυθμίσεις κώδικα, production browser verification εκκρεμεί. |
| Εξαγωγή ίδιου λογαριασμού | P1 | PARTIAL | /account/export, CSRF + fresh password + throttle + snapshot + explicit fields· test_data_export.py δεν εκτελέστηκε. |
| Διαγραφή ενεργής βάσης | P1 | PARTIAL | Υπάρχουσα transaction διαγραφής και ιστορικά τεστ· backups/logs παραμένουν εκτός. |
| Διόρθωση/περιορισμός/εναντίωση και επικοινωνία | P1 | FAIL | Οδηγίες υπάρχουν, κανάλι/διαχειριστική διαδικασία όχι. |
| Retention/backup purge και restore drill | P1 | FAIL | Χρειάζεται εγκεκριμένο schedule και δοκιμασμένη εφαρμογή. |
| Όρια κατάχρησης/DB growth | P1 | PARTIAL | Account throttle υπάρχει· quiz creation quota όχι. |
| Ρόλοι/SQL injection | P1 | PASS | Student-only registration, παραμετροποιημένα queries και ownership checks στα μονοπάτια που εξετάστηκαν. Όχι συνολική εγγύηση. |
| Stored HTML / εξαρτήσεις/CDN | P1 | PARTIAL | Έμπιστη εισαγωγή, όχι γενικός sanitizer· floating MathJax, εκκρεμεί pin/self-host και dependency audit. |
| Ανήλικοι/profiling/DPIA screening | P1 | PARTIAL | 15+ checkbox, χωρίς γονική ροή· screening/νομική βάση εκκρεμούν. |
| Live AI υπηρεσία | P2 | NOT APPLICABLE | Καμία στο runtime που εξετάστηκε· AI_COMPLIANCE.md. |
| Νομική επικαιρότητα/DSA/καταναλωτής/EAA | P1 | NEEDS VERIFICATION | Επίσημες πηγές και όρια στο LEGAL_AUDIT.md· πλήρη ενοποιημένα κείμενα/επιχειρηματικά δεδομένα λείπουν. |
| Copyright/ποιότητα εκπαιδευτικού υλικού | P2 | PARTIAL | Αρχική επιμέλεια/πηγές· όχι πλήρης άδεια και ανεξάρτητος έλεγχος ανά asset. |
| WCAG / keyboard / mobile / screen reader | P2 | PARTIAL | Στάδιο10 βελτιώσεις· οπτικός/assistive technology έλεγχος εκκρεμεί. |
| Incident response / DPA / transfers / MFA | P1 | NEEDS VERIFICATION | REQUIRED_OWNER_ACTIONS.md· όχι εφαρμοσμένη οργανωτική διαδικασία. |
| Νέα regression tests | P1 | PASS | 60 tests και JavaScript checks· βλ. VERIFICATION.md για scope και εκκρεμή browser/production verification. |
| Production deployment | P0 | NOT APPLICABLE | Δεν έγινε push/deploy σε αυτή την εργασία. |

## Επόμενη επαλήθευση όταν αποκατασταθεί η εκτέλεση

Στο τοπικό repo, μόνο με προσωρινές test databases: `node tests/test_settings.cjs`, `.venv/Scripts/python.exe -B -m unittest tests.test_data_export tests.test_legal_security tests.test_auth tests.test_design tests.test_stage6`. Έπειτα ευρύτερα tests μόνο αν ευρήματα/αλλαγές το δικαιολογούν.

Προσθήκη ελέγχων export με συμπληρωμένα κουίζ/XP και πολλούς λογαριασμούς, concurrent deletion και μεγάλη ιστορία. Επαλήθευση ότι export περιέχει ολόκληρο το ιστορικό, κανένα μυστικό ή δεδομένο άλλου χρήστη. Οπτικός έλεγχος των 7 σελίδων και export στο κινητό/πληκτρολόγιο. Network/storage inspection πριν και μετά ρητή επιλογή ρυθμίσεων· όλα τα domains/cookies και cookie flags. Έλεγχος πραγματικού Gunicorn output χωρίς URL/token. Δεν έχουν εκτελεστεί αυτά τα βήματα στην παρούσα αλλαγή.
