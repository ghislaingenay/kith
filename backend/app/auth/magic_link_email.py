"""The magic-link sign-in email: a plain-text body and a branded HTML
alternative. Mail clients ignore most CSS, so the HTML is table-based with
inline styles, no images and no web fonts, in the light Reading Room palette."""

from html import escape

# The light Reading Room tokens from frontend/app/globals.css; mail clients
# can't read CSS variables, so the values are copied here.
_ACCENT = "#2F5D4A"
_PAPER = "#F5F4EE"
_SURFACE = "#FCFBF7"
_INK = "#1F231F"
_MUTED = "#5E645C"
_LINE = "#DCDDD3"
_PALE_GREEN = "#E4EAE2"
_SERIF = "Georgia, 'Times New Roman', serif"
_SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

SUBJECT = "Your Kith sign-in link"


def plain_text_body(link: str, ttl_minutes: int) -> str:
    return (
        f"Use the link below to sign in. It expires in {ttl_minutes} minutes "
        f"and can only be used once.\n\n{link}"
    )


def html_body(link: str, ttl_minutes: int) -> str:
    href = escape(link, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SUBJECT}</title>
</head>
<body style="margin:0;padding:0;background-color:{_PAPER};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{_PAPER};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;background-color:{_SURFACE};border:1px solid {_LINE};border-radius:4px;">
<tr><td style="background-color:{_ACCENT};padding:16px 32px;border-radius:4px 4px 0 0;font-family:{_SERIF};font-size:22px;font-weight:bold;color:{_PAPER};">Kith</td></tr>
<tr><td style="padding:32px 32px 8px 32px;font-family:{_SERIF};font-size:24px;line-height:1.3;color:{_INK};">Sign in to Kith</td></tr>
<tr><td style="padding:0 32px 24px 32px;font-family:{_SANS};font-size:15px;line-height:1.5;color:{_INK};">Use the button below to sign in to your workspace.</td></tr>
<tr><td style="padding:0 32px 24px 32px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="background-color:{_ACCENT};border-radius:4px;">
<a href="{href}" style="display:inline-block;padding:12px 24px;font-family:{_SANS};font-size:15px;font-weight:bold;color:#FFFFFF;text-decoration:none;">Sign in</a>
</td></tr></table>
</td></tr>
<tr><td style="padding:0 32px 16px 32px;font-family:{_SANS};font-size:14px;line-height:1.5;color:{_INK};"><strong>Expires in {ttl_minutes} minutes and works once.</strong></td></tr>
<tr><td style="padding:0 32px 24px 32px;font-family:{_SANS};font-size:13px;line-height:1.5;color:{_MUTED};">
If the button doesn't work, copy this link into your browser:
<div style="margin-top:8px;padding:12px;background-color:{_PALE_GREEN};border-radius:4px;font-family:{_SANS};font-size:13px;color:{_INK};word-break:break-all;"><a href="{href}" style="color:{_ACCENT};">{href}</a></div>
</td></tr>
<tr><td style="padding:16px 32px 32px 32px;border-top:1px solid {_LINE};font-family:{_SANS};font-size:13px;line-height:1.5;color:{_MUTED};">Didn't ask for this? You can ignore this email.</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
