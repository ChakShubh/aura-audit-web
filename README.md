# ⚡ AuraAudit

> **Real-time Web Accessibility (WCAG 2.2) & Serverless Performance Diagnostics Engine**

AuraAudit is an interactive web engineering tool. It combines pure Python DOM inspection with **Amazon Bedrock (Nova Micro)** to audit any web URL against WCAG 2.2 (Level A & AA) standards, measure HTTP telemetry, and deliver copy-paste code remediation patches with zero heavy browser overhead.

---

## 🌟 Features

- **WCAG 2.2 Level A/AA Analysis:** Evaluates missing `alt` tags, heading hierarchies, form input bindings, unlabelled buttons, and document lang attributes.
- **Serverless Performance Telemetry:** Measures Time to First Byte (TTFB), payload weight, caching directives, and security headers (CSP, HSTS).
- **Automated Code Remediation:** Powered by Amazon Bedrock Nova Micro, generating concrete HTML/CSS/JS patch diffs for identified violations.
- **Zero-Dependency Architecture:** Python 3.12+ backend running exclusively on AWS Lambda Free Tier primitives.
- **Modern Responsive Interface:** Glassmorphic dashboard built for instant accessibility scanning.

---

## 🛠️ Tech Stack

- **Frontend:** HTML5, Modern CSS (Glassmorphism), Vanilla JavaScript, Google Fonts (`Plus Jakarta Sans`, `JetBrains Mono`)
- **Hosting:** AWS Amplify
- **Compute:** AWS Lambda (`Python 3.12`)
- **Foundation Model:** Amazon Bedrock (`amazon.nova-micro-v1:0`)
- **APIs:** Lambda Function URL (CORS enabled)
