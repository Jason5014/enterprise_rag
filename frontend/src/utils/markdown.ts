import { Marked } from 'marked'
import type { Config } from 'dompurify'
import createDOMPurify from 'dompurify'

const DOMPurify = createDOMPurify(window)

const markedInstance = new Marked({
  async: false,
  breaks: true,
  gfm: true,
})

const ALLOWED: Config = {
  ALLOWED_TAGS: [
    'p', 'br', 'strong', 'b', 'em', 'i', 's', 'del', 'ins',
    'code', 'pre', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'blockquote', 'a', 'hr', 'span', 'div',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
  ],
  ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
  RETURN_TRUSTED_TYPE: false,
}

export function renderMarkdown(text: string): string {
  if (!text) return ''
  const raw = markedInstance.parse(text) as string
  return DOMPurify.sanitize(raw, ALLOWED) as string
}
