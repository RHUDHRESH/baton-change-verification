async (page) => {
  const origin = 'http://127.0.0.1:8000';
  const response = await page.request.get(origin + '/api/demo?seed=7');
  if (!response.ok()) throw new Error('Live fixture unavailable for browser test');
  const data = await response.json();
  const payload = "<img src=x onerror='window.__batonXSS=1'><svg onload='window.__batonXSS=2'></svg>";
  data.leaver_name = payload;
  for (const lane of Object.values(data.lanes)) {
    if (lane.failures.length) lane.failures[0].duty_name = payload;
    for (const row of lane.failures) for (const source of row.sources) source.text = payload;
  }
  await page.addInitScript(() => { window.__batonXSS = 0; });
  const handler = route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  await page.route('**/api/demo*', handler);
  let evidence;
  try {
    await page.goto(origin);
    await page.getByRole('button', { name: 'View proof for ' + payload, exact: true }).click();
    const executed = await page.evaluate(() => window.__batonXSS);
    const markupNodes = await page.locator('#proof img, #proof svg, #leaver-name img, #leaver-name svg').count();
    if (executed !== 0 || markupNodes !== 0) throw new Error('Script-bearing markup was interpreted');
    evidence = { attack: 'DOM script injection through API name, duty and evidence', outcome: 'blocked', executed, markupNodes, nameRenderedAsText: await page.locator('#leaver-name').textContent() === payload };
    await page.screenshot({ path: 'output/playwright/redteam-xss.png' });
  } finally {
    await page.unroute('**/api/demo*', handler);
    await page.goto(origin);
  }
  return evidence;
}
