# Dataset: FounderDesk

Startup scheme matcher collecting DPIIT recognition, seed fund, tax benefit, and state startup policy documents for student founders.

- **Start target:** 10 documents covering DPIIT recognition, seed fund, tax benefits, and state startup policies
- **Full target:** 200 documents across central and state startup schemes
- **Collected by:** `scripts/fetch.py` as `examate-student-bot` (https://github.com/Styrish007/prince28-fin08-founderdesk): robots.txt respected, at most 4 requests at once, 0.5 s between requests to one site.

## Where the documents come from

- https://www.startupindia.gov.in/
- https://startuptn.in/
- https://startuptn.in/pdf/Tamil-Nadu-Startup-and-Innovation-Policy-2023.pdf
- https://www.startupindia.gov.in/content/sih/en/faqs.html
- https://www.startupindia.gov.in/content/sih/en/state-startup-policies.html
- https://www.startupindia.gov.in/content/sih/en/startupgov/self-certification.html
- https://www.startupindia.gov.in/content/sih/en/recognition-page.html
- https://www.startupindia.gov.in/content/sih/en/startup-scheme.html
- https://www.startupindia.gov.in/content/sih/en/building-and-managing-a-business.html
- https://www.startupindia.gov.in/content/sih/en/reources/knowledge-bank.html

## Terms I follow

StartupTN Tamil Nadu Startup and Innovation Policy 2023 (PDF); Startup India scheme pages, FAQs, state policies, self-certification, recognition, knowledge bank (Government of India).

- Every answer links to the original document.
- No personal data is collected.

<!-- generated:start -->
| Source | File | Pages | Size kB | Chars | Tokens | Licence |
|---|---|---|---:|---:|---:|---|
| startup-india-faqs | faqs.html | 1 | 304.5 | 24,170 | 6,042 | Government of India - Startup India FAQs page |
| startuptn-policy | Tamil-Nadu-Startup-and-Innovation-Policy-2023.pdf | 56 | 5,091.3 | 7,257 | 1,814 | Government of Tamil Nadu - Tamil Nadu Startup and Innovation Policy 2023 PDF |
| startuptn | index.html | 1 | 4.4 | 56 | 14 | Government of Tamil Nadu portal - public scheme information; reproduce with attribution |
| startup-india | index.html | 1 | 597.7 | 21,930 | 5,482 | Government of India portal - public scheme information; reproduce with attribution |
| startup-india-state-policies | state-startup-policies.html | 1 | 266.8 | 7,191 | 1,797 | Government of India - State/UT startup policies page |
| startup-india-self-cert | self-certification.html | 1 | 273.8 | 7,919 | 1,979 | Government of India - DPIIT self-certification page |
| startup-india-recognition | recognition-page.html | 1 | 483.3 | 19,998 | 4,999 | Government of India - DPIIT recognition page |
| startup-india-managing-business | building-and-managing-a-business.html | 1 | 265.8 | 6,563 | 1,640 | Government of India - Building and managing a business page |
| startup-india-scheme | startup-scheme.html | 1 | 338.4 | 18,451 | 4,612 | Government of India - Startup India scheme page |
| startup-india-knowledge-bank | knowledge-bank.html | 1 | 272.1 | 6,696 | 1,674 | Government of India - Startup Guidebook / knowledge bank |
| **Total** | 10 files | **65** | | **120,231** | **30,053** | |
<!-- generated:end -->

## Known gaps

- Only 10 of the 200-document full target collected today; the rest will be downloaded over the coming week (the fetcher resumes where it stopped).
- Tamil Nadu Startup and Innovation Policy 2023 PDF captured; other state scheme PDFs may need door 4 (by hand) if the portal blocks bots.

## Parsing coverage

Parsed documents ÷ (parsed + failed): 10 ÷ (10 + 0) = 100% of files
Parsed pages ÷ (parsed + failed): 77 ÷ (77 + 0) = 100% of pages
