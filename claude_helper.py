import anthropic
import base64
import os

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are an expert Automotive Quality Engineer assistant with deep knowledge in:
- APQP, PPAP, PFMEA, Control Plans
- 8D Problem Solving methodology
- GP12 / Customer Specific Requirements
- IATF 16949 and ISO 9001 standards
- Statistical Process Control (SPC)
- Corrective and Preventive Actions (CAPA)
- PPM tracking and quality metrics
- Supplier quality management

Always respond in the same language the user writes in.
Be concise, technical, and actionable.
When generating 8D reports, use the standard D1-D8 format.
When generating quality alerts, use a clear structured format."""

async def ask_claude(question: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}]
    )
    return message.content[0].text

async def analyze_pdf_text(pdf_text: str) -> str:
    prompt = f"""Analyze this quality document and provide:
1. Key findings
2. Main defects or risks identified
3. Recommended actions

Document content:
{pdf_text}"""
    return await ask_claude(prompt)

async def generate_8d(problem_description: str) -> str:
    prompt = f"""Generate a complete 8D report for the following problem:

{problem_description}

Format each discipline as D1 through D8 with clear, actionable content."""
    return await ask_claude(prompt)

async def generate_quality_alert(image1_data: bytes, image2_data: bytes, description: str) -> str:
    image1_b64 = base64.standard_b64encode(image1_data).decode("utf-8")
    image2_b64 = base64.standard_b64encode(image2_data).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": f"Generate a quality alert based on these two images. Additional context: {description}\n\nFormat the alert as:\n🚨 QUALITY ALERT\n📅 Date: [today]\n🔍 Defect Description:\n📸 Visual Evidence: [describe what you see in both images]\n⚠️ Risk Level: [Low/Medium/High]\n✅ Acceptance Criteria:\n❌ Rejection Criteria:\n🔧 Recommended Action:\n📋 Containment:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image1_b64}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image2_b64}}
            ]
        }]
    )
    return message.content[0].text