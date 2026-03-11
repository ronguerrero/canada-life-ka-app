"""Knowledge Agent chat integration using the agent/v1/responses API."""

import json
import re
import aiohttp
from server.config import get_host_url, get_token, get_service_principal_token, AGENT_ENDPOINT_NAME


def _strip_xml_tags(text: str) -> str:
    """Remove XML/HTML-style tags from text (e.g., <name>...</name>)."""
    # Remove opening and closing tags like <name>...</name>
    text = re.sub(r'<[^>]+>[^<]*</[^>]+>', '', text)
    # Remove standalone tags like <tag> or </tag>
    text = re.sub(r'</?[^>]+>', '', text)
    return text.strip()


def _format_citations(text: str) -> str:
    """Convert verbose footnotes to inline hover links."""
    print(f"[DEBUG] Formatting citations, input length: {len(text)}")

    # First, extract all footnote definitions [^id]: text
    footnotes = {}

    def extract_footnote(match):
        citation_id = match.group(1)
        citation_text = match.group(2).strip()

        # Extract document link if present
        doc_link_match = re.search(r'\[([^\]]+)\]\((https?://[^\)]+)\)', citation_text)

        # Store footnote with short preview and link
        preview = citation_text[:100].strip()
        if len(citation_text) > 100:
            preview += "..."

        doc_url = None
        doc_name = None
        if doc_link_match:
            doc_name = doc_link_match.group(1)
            doc_url = doc_link_match.group(2).split('#')[0]  # Remove fragment
            # Extract filename
            filename_match = re.search(r'/([^/]+\.(?:docx?|pdf|xlsx?|pptx?|txt))$', doc_url, re.IGNORECASE)
            if filename_match:
                doc_name = filename_match.group(1)

        footnotes[citation_id] = {
            'preview': preview,
            'url': doc_url,
            'name': doc_name
        }

        return ''  # Remove footnote definition from text

    # Extract all footnote definitions
    text = re.sub(
        r'\[\^([^\]]+)\]:\s*(.+?)(?=\n\[\^|\n\n|\Z)',
        extract_footnote,
        text,
        flags=re.DOTALL
    )

    print(f"[DEBUG] Found {len(footnotes)} footnote definitions: {list(footnotes.keys())}")

    # Replace inline footnote references [^id] with hover links
    def replace_reference(match):
        citation_id = match.group(1)
        if citation_id in footnotes:
            fn = footnotes[citation_id]
            if fn['url'] and fn['name']:
                # Create inline link with hover text
                return f'<sup><a href="{fn["url"]}" title="{fn["preview"]}" target="_blank">[{fn["name"]}]</a></sup>'
            else:
                return f'<sup title="{fn["preview"]}">[source]</sup>'
        return match.group(0)  # Keep original if not found

    text = re.sub(r'\[\^([^\]]+)\]', replace_reference, text)

    # Clean up extra whitespace
    text = re.sub(r'\n\n\n+', '\n\n', text)

    return text.strip()


def _extract_agent_response(data: dict) -> str:
    """
    Extract the text content from an agent/v1/responses response.

    The response format is:
    {
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "actual answer text"}
                ]
            }
        ]
    }
    """
    if not isinstance(data, dict):
        return str(data)

    output = data.get("output")

    # Pattern 1: output is a list of message objects (agent/v1/responses)
    if isinstance(output, list):
        text_parts = []
        for item in output:
            if isinstance(item, dict):
                # Check for nested content array
                content = item.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            text = block.get("text", "")
                            if text:
                                text_parts.append(text)
                elif isinstance(content, str):
                    text_parts.append(content)

                # If no content array, check for direct text
                if not text_parts:
                    text = item.get("text", "")
                    if text:
                        text_parts.append(text)
            elif isinstance(item, str):
                text_parts.append(item)

        if text_parts:
            text = _strip_xml_tags("\n\n".join(text_parts))
            return _format_citations(text)

    # Pattern 2: output is a string
    if isinstance(output, str):
        text = _strip_xml_tags(output.strip())
        return _format_citations(text)

    # Pattern 3: output is a dict with content/text
    if isinstance(output, dict):
        text = _strip_xml_tags(output.get("content", output.get("text", str(output))))
        return _format_citations(text)

    # Pattern 4: choices array (OpenAI-compatible)
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        text = _strip_xml_tags(msg.get("content", ""))
        return _format_citations(text)

    # Pattern 5: direct content field
    if "content" in data:
        text = _strip_xml_tags(str(data["content"]))
        return _format_citations(text)

    # Fallback: return pretty-printed JSON
    return json.dumps(data, indent=2)


async def chat_with_agent(
    messages: list[dict],
    request=None,
    endpoint_name: str | None = None,
) -> dict:
    """
    Send messages to the knowledge agent endpoint and return the response.

    The knowledge agent uses the agent/v1/responses task type which expects
    an 'input' field with conversation history, not the standard 'messages' format.

    Args:
        messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
        request: FastAPI request object (not used, kept for compatibility)
        endpoint_name: Override for the agent endpoint name

    Returns:
        {"content": str, "sources": list[dict] | None}
    """
    endpoint = endpoint_name or AGENT_ENDPOINT_NAME
    # For authorization:user mode, use the user token (gets resource permissions from app.yaml)
    token = get_token(request)
    if not token:
        return {"content": "Error: No authentication token available", "sources": None}

    host = get_host_url()
    print(f"[DEBUG] Using token for agent endpoint: {endpoint}")

    url = f"{host}/serving-endpoints/{endpoint}/invocations"

    payload = {
        "input": messages,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    print(f"[DEBUG] Calling agent endpoint: {url}")
    print(f"[DEBUG] Token available: {bool(token)}, Token length: {len(token) if token else 0}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"[ERROR] Agent API error ({response.status}): {error_text}")
                    print(f"[ERROR] Request URL: {url}")
                    print(f"[ERROR] Request headers: {headers}")
                    return {
                        "content": f"Error {response.status}: {error_text}",
                        "sources": None,
                    }

                data = await response.json()
                print(f"[DEBUG] Agent response received successfully")
                content = _extract_agent_response(data)

                return {"content": content, "sources": None}

    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"[ERROR] Agent chat exception: {error_msg}")
        print(f"[ERROR] Traceback: {error_trace}")
        return {"content": f"Error: {error_msg}", "sources": None}


async def stream_chat_with_agent(
    messages: list[dict],
    request=None,
    endpoint_name: str | None = None,
):
    """
    Stream responses from the knowledge agent endpoint.

    Note: Agent endpoints may not support true streaming. This sends the
    request and yields the complete response.
    """
    endpoint = endpoint_name or AGENT_ENDPOINT_NAME
    # For authorization:user mode, use the user token (gets resource permissions from app.yaml)
    token = get_token(request)
    if not token:
        yield "Error: No authentication token available"
        return

    host = get_host_url()
    print(f"[DEBUG] Using token for streaming agent endpoint: {endpoint}")

    url = f"{host}/serving-endpoints/{endpoint}/invocations"

    payload = {
        "input": messages,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield f"Error: {error_text}"
                    return

                data = await response.json()
                content = _extract_agent_response(data)
                yield content

    except Exception as e:
        yield f"Error: {str(e)}"
