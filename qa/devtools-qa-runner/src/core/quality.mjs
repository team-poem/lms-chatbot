export function analyzeQuality(r, quality = {}) {
  const failures = [];
  const warnings = [];

  for (const msg of r.consoleMessages?.consoleMessages || []) {
    if (msg.type === 'error') warnings.push(`Console error: ${msg.text}`);
  }

  for (const req of r.networkRequests?.networkRequests || []) {
    const status = Number(req.status);
    const isFavicon = String(req.url).endsWith('/favicon.ico');
    if (status >= 500) failures.push(`${req.method} ${req.url} -> ${req.status}`);
    else if (status >= 400 && !(quality.ignoreFavicon404 && isFavicon)) warnings.push(`${req.method} ${req.url} -> ${req.status}`);
  }

  for (const score of r.lighthouse?.lighthouseResult?.summary?.scores || []) {
    if (quality.ignoreSeo && score.id === 'seo') continue;
    if (typeof score.score === 'number' && score.score < (quality.lighthouseFailBelow ?? 0.8)) {
      failures.push(`Low Lighthouse ${score.title}: ${score.score}`);
    } else if (typeof score.score === 'number' && score.score < (quality.lighthouseWarnBelow ?? 0.9)) {
      warnings.push(`Borderline Lighthouse ${score.title}: ${score.score}`);
    }
  }

  return { status: failures.length ? 'fail' : warnings.length ? 'warning' : 'pass', failures, warnings };
}
