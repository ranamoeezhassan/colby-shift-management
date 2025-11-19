function aiEscapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function aiLinkifyRelativeCodes(html) {
  if (!html) return "";
  let result = html;

  // 1) Turn <code>/path</code> into a clickable chip.
  result = result.replace(
    /<code>(\/[^<\s]*)<\/code>/g,
    '<a href="$1" class="ai-link-chip" target="_blank" rel="noopener noreferrer"><code>$1</code></a>'
  );

  // 2) Turn bare /relative/paths in plain text into clickable links.
  //    We look for paths that are preceded by start-of-string, whitespace, or '>'
  //    or '(' to avoid touching href attributes but catch patterns like
  //    '(/outputs/student/2)'.
  result = result.replace(
    /(^|[\s>(])((\/[A-Za-z0-9_\-\/.?=&%#]+))/g,
    '$1<a href="$2" class="ai-md-link" target="_blank" rel="noopener noreferrer">$2</a>'
  );

  return result;
}

function aiRenderMarkdown(markdown) {
  if (!markdown) return "";
  let text = String(markdown).trim();

  // Normalize absolute URLs (https://host/path) into relative paths (/path)
  // so the UI never shows full domains like https://yourapp.com.
  text = text.replace(/https?:\/\/[^\/\s]+(\/[^\s)>]*)/gi, "$1");

  // Clean up any raw HTML tags the model might have produced. We want the
  // assistant to speak in Markdown, not raw HTML.
  // Drop <pre> wrappers entirely and turn <code>...</code> into backticks.
  text = text.replace(/<pre[^>]*>/gi, "").replace(/<\/pre>/gi, "");
  text = text.replace(/<code[^>]*>/gi, "`").replace(/<\/code>/gi, "`");

  // Code fences ```...``` – keep the inner content, remove the fence markers.
  // That way URLs inside fences still get linkified like normal text.
  text = text.replace(/```([\s\S]*?)```/g, (_, code) => code.trim());

  // Escape any remaining HTML.
  text = aiEscapeHtml(text);

  // Markdown links [label](/relative/path)
  text = text.replace(
    /\[([^\]]+)\]\((\/[^)]+)\)/g,
    '<a href="$2" class="ai-md-link" target="_blank" rel="noopener noreferrer">$1</a>'
  );

  // Inline bold and italics (very simple, non-nested).
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Inline code `...`
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");

  const lines = text.split(/\r?\n/);
  const html = [];
  let inUl = false;
  let inOl = false;

  function closeLists() {
    if (inUl) {
      html.push("</ul>");
      inUl = false;
    }
    if (inOl) {
      html.push("</ol>");
      inOl = false;
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      closeLists();
      continue;
    }

    const ulMatch = /^[-*]\s+(.+)$/.exec(line);
    if (ulMatch) {
      if (!inUl) {
        closeLists();
        html.push('<ul class="ai-list">');
        inUl = true;
      }
      html.push(`<li>${ulMatch[1]}</li>`);
      continue;
    }

    const olMatch = /^(\d+)\.\s+(.+)$/.exec(line);
    if (olMatch) {
      if (!inOl) {
        closeLists();
        html.push('<ol class="ai-list ai-list-ordered">');
        inOl = true;
      }
      html.push(`<li>${olMatch[2]}</li>`);
      continue;
    }

    // Regular paragraph.
    closeLists();
    html.push(`<p>${line}</p>`);
  }

  closeLists();
  const rawHtml = html.join("");
  return aiLinkifyRelativeCodes(rawHtml);
}

function aiStreamAnswer(markdown, element, getHtml) {
  const text = String(markdown || "");
  if (!text) {
    element.innerHTML = "";
    return;
  }

  let index = 0;
  const total = text.length;
  let cancelled = false;

  // Attach a simple handle so a new request can cancel previous streams.
  if (element._aiCancelStream && typeof element._aiCancelStream === "function") {
    element._aiCancelStream();
  }
  element._aiCancelStream = () => {
    cancelled = true;
  };

  element.innerHTML = "";

  function step() {
    if (cancelled) {
      return;
    }
    if (index >= total) {
      element.innerHTML = getHtml(text);
      return;
    }
    const partial = text.slice(0, index + 1);
    element.innerHTML = getHtml(partial);
    index += 2; // advance a little faster than 1 char per frame
    window.requestAnimationFrame(step);
  }

  window.requestAnimationFrame(step);
}

document.addEventListener("DOMContentLoaded", () => {
  const trigger = document.getElementById("ai-trigger-button");
  const backdrop = document.getElementById("ai-ask-bar-backdrop");
  const container = document.getElementById("ai-ask-bar");
  const closeButton = document.getElementById("ai-close-button");
  const form = document.getElementById("ai-ask-bar-form");
  const input = document.getElementById("ai-question-input");
  const answerArea = document.getElementById("ai-answer-area");

  let hasAskedQuestion = false;

  if (!trigger || !container || !form || !input || !answerArea) {
    // If the elements aren't present, don't try to wire anything up.
    return;
  }

  function openBar() {
    container.hidden = false;
    container.setAttribute("aria-hidden", "false");
    if (backdrop) {
      backdrop.hidden = false;
    }
    // Allow the browser to paint before adding the open class for smooth animation.
    window.requestAnimationFrame(() => {
      container.classList.add("ai-open");
      if (backdrop) {
        backdrop.classList.add("ai-open");
      }
    });
    try {
      input.focus();
    } catch (_) {
      // Ignore focus errors.
    }
  }

  function closeBar() {
    container.classList.remove("ai-open");
    if (backdrop) {
      backdrop.classList.remove("ai-open");
    }
    // Wait for animation to finish before fully hiding.
    setTimeout(() => {
      container.hidden = true;
      container.setAttribute("aria-hidden", "true");
      if (backdrop) {
        backdrop.hidden = true;
      }
    }, 200);
  }

  trigger.addEventListener("click", () => {
    const isHidden = container.hidden || container.getAttribute("aria-hidden") === "true";
    if (isHidden) {
      openBar();
    } else {
      closeBar();
    }
  });

  if (backdrop) {
    backdrop.addEventListener("click", () => closeBar());
  }

  if (closeButton) {
    closeButton.addEventListener("click", () => closeBar());
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeBar();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) {
      return;
    }

    // First real question expands the dialog to full width.
    if (!hasAskedQuestion) {
      hasAskedQuestion = true;
      container.classList.add("ai-expanded");
    }

    aiStreamAnswer(
      "Thinking about the best place for that…",
      answerArea,
      aiRenderMarkdown
    );

    try {
      const response = await fetch("/api/ai/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({
          question,
          current_path: window.location.pathname,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (response.ok && data.answer) {
        aiStreamAnswer(data.answer, answerArea, aiRenderMarkdown);
      } else if (data.error) {
        answerArea.innerHTML = `<p class="ai-answer-error">${aiEscapeHtml(
          data.error
        )}</p>`;
      } else {
        answerArea.innerHTML =
          '<p class="ai-answer-error">Sorry, I couldn&apos;t get a helpful answer. Please try rephrasing your question.</p>';
      }
    } catch (error) {
      console.error("AI assistant request failed:", error);
      answerArea.innerHTML =
        '<p class="ai-answer-error">Sorry, there was a problem contacting the assistant. Please try again in a moment.</p>';
    }
  });
});


