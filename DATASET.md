# Dataset: FounderDesk

Startup scheme matcher collecting DPIIT recognition, seed fund, tax benefit, and state startup policy documents for student founders.

- **Start target:** 10 documents covering DPIIT recognition, seed fund, tax benefits, and state startup policies
- **Full target:** 200 documents across central and state startup schemes
- **Collected by:** `scripts/fetch.py` as `examate-student-bot` (https://github.com/Styrish007/prince28-fin08-founderdesk): robots.txt respected, at most 4 requests at once, 0.5 s between requests to one site.

## Where the documents come from

- https://www.startupindia.gov.in/
- https://startuptn.in/
- https://startuptn.in/pdf/Tamil-Nadu-Startup-and-Innovation-Policy-2023.pdf
- https://en.wikipedia.org/wiki/Startup_India
- https://en.wikipedia.org/wiki/Make_in_India
- https://en.wikipedia.org/wiki/Stand-Up_India
- https://en.wikipedia.org/wiki/Digital_India
- https://en.wikipedia.org/wiki/Atmanirbhar_Bharat
- https://en.wikipedia.org/wiki/Pradhan_Mantri_Mudra_Yojana
- https://en.wikipedia.org/wiki/Skill_India

## Terms I follow

StartupTN Tamil Nadu Startup and Innovation Policy 2023 (PDF); Startup India portal; Wikipedia (CC BY-SA 4.0, attribution required).

- Every answer links to the original document.
- No personal data is collected.

<!-- generated:start -->
| Source | File | Pages | Size kB | Chars | Tokens | Licence |
|---|---|---|---:|---:|---:|---|
| startuptn | index.html | 1 | 4.4 | 56 | 14 | Government of Tamil Nadu portal - public scheme information; reproduce with attribution |
| wikipedia | Startup_India.html | 1 | 119.0 | 8,873 | 2,218 | CC BY-SA 4.0 |
| startup-india | index.html | 1 | 597.7 | 21,930 | 5,482 | Government of India portal - public scheme information; reproduce with attribution |
| wikipedia | Make_in_India.html | 1 | 502.6 | 44,976 | 11,244 | CC BY-SA 4.0 |
| startuptn-policy | Tamil-Nadu-Startup-and-Innovation-Policy-2023.pdf | 56 | 5,091.3 | 7,257 | 1,814 | Government of Tamil Nadu - Tamil Nadu Startup and Innovation Policy 2023 PDF |
| wikipedia | Stand-Up_India.html | 1 | 116.2 | 7,870 | 1,967 | CC BY-SA 4.0 |
| wikipedia | Digital_India.html | 1 | 223.0 | 19,446 | 4,861 | CC BY-SA 4.0 |
| wikipedia | Skill_India.html | 1 | 133.9 | 12,144 | 3,036 | CC BY-SA 4.0 |
| wikipedia | Atmanirbhar_Bharat.html | 1 | 351.7 | 28,998 | 7,249 | CC BY-SA 4.0 |
| wikipedia | Pradhan_Mantri_Mudra_Yojana.html | 1 | 1,154.5 | 123,302 | 30,825 | CC BY-SA 4.0 |
| **Total** | 10 files | **65** | | **274,852** | **68,710** | |
<!-- generated:end -->

## Known gaps

- Only 10 of the 200-document full target collected today; the rest will be downloaded over the coming week (the fetcher resumes where it stopped).
- Tamil Nadu Startup and Innovation Policy 2023 PDF captured; other state scheme PDFs may need door 4 (by hand) if the portal blocks bots.
