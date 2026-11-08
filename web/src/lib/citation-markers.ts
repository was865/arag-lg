const CITATION_MARKER_RE = /(?:\[(\d+)\]|［(\d+)］|【(\d+)】)/g;

export function citationMarkerPattern(): RegExp {
  return new RegExp(CITATION_MARKER_RE.source, "g");
}

export function citationMarkerHasMatch(text: string): boolean {
  return new RegExp(CITATION_MARKER_RE.source).test(text);
}

export function citationMarkerNumber(match: RegExpExecArray): string {
  return match[1] ?? match[2] ?? match[3] ?? "";
}

export function normalizeCitationMarkers(text: string): string {
  return text.replace(citationMarkerPattern(), (_raw, ascii: string | undefined, full: string | undefined, lenticular: string | undefined) => {
    const n = ascii ?? full ?? lenticular;
    return n ? `[${n}]` : _raw;
  });
}

export function extractCitationNums(text: string): number[] {
  return [...text.matchAll(citationMarkerPattern())]
    .map((match) => Number(citationMarkerNumber(match)))
    .filter((n) => Number.isFinite(n));
}
