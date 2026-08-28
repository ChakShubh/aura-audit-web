import json
import time
import base64
import ssl
import traceback
import urllib.request
import urllib.error
from html.parser import HTMLParser
import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

class DOMInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lang = None
        self.title = ""
        self.in_title = False
        self.images_total = 0
        self.images_missing_alt = 0
        self.headings = []
        self.forms_total = 0
        self.inputs_total = 0
        self.inputs_missing_label = 0
        self.buttons_total = 0
        self.buttons_empty = 0
        self.curr_tag = None

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        self.curr_tag = tag

        if tag == "html" and "lang" in attr_dict:
            self.lang = attr_dict["lang"]

        elif tag == "title":
            self.in_title = True

        elif tag == "img":
            self.images_total += 1
            if "alt" not in attr_dict or not attr_dict["alt"].strip():
                self.images_missing_alt += 1

        elif tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            self.headings.append({"level": tag, "text": ""})

        elif tag == "form":
            self.forms_total += 1

        elif tag == "input":
            input_type = attr_dict.get("type", "text").lower()
            if input_type not in ["hidden", "submit", "button", "reset"]:
                self.inputs_total += 1
                has_aria = "aria-label" in attr_dict or "aria-labelledby" in attr_dict
                has_id = "id" in attr_dict
                if not has_aria and not has_id:
                    self.inputs_missing_label += 1

        elif tag == "button":
            self.buttons_total += 1
            if "aria-label" not in attr_dict and "aria-labelledby" not in attr_dict:
                self.buttons_empty += 1

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title += text
        elif self.headings and self.headings[-1]["text"] == "":
            self.headings[-1]["text"] = text[:60]
        elif self.curr_tag == "button" and self.buttons_empty > 0 and len(text) > 0:
            self.buttons_empty -= 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        self.curr_tag = None


def audit_with_bedrock(url, telemetry, headers_info):
    system_prompt = (
        "You are an expert Web Accessibility (WCAG 2.2 Level A/AA) and Web Performance Auditor. "
        "Analyze the provided DOM telemetry, structural metrics, and HTTP headers. "
        "Produce an accurate, highly actionable audit strictly matching the specified JSON format. "
        "Ensure all recommendations are compliant with WCAG 2.2 criteria. "
        "Respond ONLY with valid JSON, no conversational markdown before or after."
    )

    user_prompt = f"""
Audit the following website data against WCAG 2.2 standards:
Target URL: {url}
HTTP Response Time (TTFB): {telemetry.get('ttfb_ms')} ms
Payload Size: {telemetry.get('payload_kb')} KB
HTML Lang Attribute: {telemetry.get('html_lang')}
Title Tag: {telemetry.get('title')}
Total Images: {telemetry.get('images_total')} (Missing Alt: {telemetry.get('images_missing_alt')})
Total Inputs: {telemetry.get('inputs_total')} (Missing Labels/Aria: {telemetry.get('inputs_missing_label')})
Total Buttons: {telemetry.get('buttons_total')} (Missing Label/Name: {telemetry.get('buttons_empty')})
Heading Structure: {json.dumps(telemetry.get('headings')[:10])}
HTTP Security/Caching Headers: {json.dumps(headers_info)}

Required JSON Schema:
{{
  "scores": {{
    "accessibility": 85,
    "performance": 90,
    "semantics": 80,
    "overall": 85
  }},
  "summary": "2-3 sentences summarizing the key accessibility and performance posture.",
  "issues": [
    {{
      "severity": "CRITICAL",
      "wcag_criterion": "WCAG 2.2 - 1.1.1 Non-text Content (Level A)",
      "title": "Images missing alt text",
      "description": "Found images without alt descriptions.",
      "code_snippet_remediation": "<img src='logo.png' alt='Company Logo' />"
    }}
  ],
  "quick_wins": [
    "Add lang='en' to the <html> root element"
  ]
}}
"""

    request_body = {
        "system": [{"text": system_prompt}],
        "messages": [
            {
                "role": "user",
                "content": [{"text": user_prompt}]
            }
        ],
        "inferenceConfig": {
            "maxTokens": 2048,
            "temperature": 0.2
        }
    }

    response = bedrock.invoke_model(
        modelId="amazon.nova-micro-v1:0",
        body=json.dumps(request_body),
        accept="application/json",
        contentType="application/json"
    )

    response_body = json.loads(response['body'].read())
    raw_text = response_body["output"]["message"]["content"][0]["text"].strip()

    # Strip markdown fences if present
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].split("```")[0].strip()

    return json.loads(raw_text)


def lambda_handler(event, context):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
    }

    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": json.dumps({"status": "ok"})}

    try:
        # Decode body if base64 encoded
        raw_body = event.get("body", "{}")
        if event.get("isBase64Encoded", False):
            raw_body = base64.b64decode(raw_body).decode('utf-8')

        data = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
        target_url = data.get("url", "").strip()

        if not target_url:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({"error": "Missing 'url' parameter in request body."})
            }

        if not target_url.startswith("http://") and not target_url.startswith("https://"):
            target_url = "https://" + target_url

        # SSL & User-Agent Bypass
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            target_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )

        start_time = time.time()
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            raw_html = resp.read()
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            html_text = raw_html.decode('utf-8', errors='ignore')
            resp_headers = dict(resp.info())

        payload_kb = round(len(raw_html) / 1024, 2)

        inspector = DOMInspector()
        inspector.feed(html_text[:120000])

        telemetry = {
            "ttfb_ms": elapsed_ms,
            "payload_kb": payload_kb,
            "html_lang": inspector.lang or "MISSING",
            "title": inspector.title or "MISSING",
            "images_total": inspector.images_total,
            "images_missing_alt": inspector.images_missing_alt,
            "inputs_total": inspector.inputs_total,
            "inputs_missing_label": inspector.inputs_missing_label,
            "buttons_total": inspector.buttons_total,
            "buttons_empty": max(0, inspector.buttons_empty),
            "headings": inspector.headings
        }

        headers_info = {
            "content_encoding": resp_headers.get("Content-Encoding", "None"),
            "cache_control": resp_headers.get("Cache-Control", "None"),
            "content_security_policy": "Present" if "Content-Security-Policy" in resp_headers else "Missing",
            "strict_transport_security": "Present" if "Strict-Transport-Security" in resp_headers else "Missing"
        }

        report = audit_with_bedrock(target_url, telemetry, headers_info)
        report["target_url"] = target_url
        report["telemetry_raw"] = telemetry

        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps(report)
        }

    except Exception as e:
        print("Detailed Error Traceback:")
        traceback.print_exc()
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({"error": str(e)})
        }
    