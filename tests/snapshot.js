// Collects every visible number on the site into one object, for before/after comparison.
// Run in the page (Chrome devtools or the browser tool) after data has loaded.
(async () => {
  const w = ms => new Promise(r => setTimeout(r, ms));
  const $ = id => document.getElementById(id);
  const txt = el => (el ? el.innerText.replace(/\s+/g, ' ').trim() : null);
  const go = async h => { location.hash = h; await w(400); };
  const out = { errors: [] };
  window.addEventListener('error', e => out.errors.push(String(e.message)));

  await go('#leaders');
  out.leaders = { count: txt($('sLeaders')), idx: txt($('sIdx')), nh: txt($('sNH')), sector: txt($('sSec')),
    rows: document.querySelectorAll('#tb tr').length, first: txt(document.querySelector('#tb tr')) };
  for (const f of ['rs80', 'nh', 'trend', 'near', 'nearma', 'setup']) {
    const b = document.querySelector(`[data-f="${f}"]`); b.click(); await w(80);
    out.leaders['f_' + f] = document.querySelectorAll('#tb tr').length; b.click(); await w(80);
  }

  await go('#strategies');
  out.strategies = [...document.querySelectorAll('#stCards .scard')].map(c => txt(c.querySelector('.top')));
  out.scorecard = [...document.querySelectorAll('#scTb tr')].map(txt);

  await go('#scanners');
  out.scanners = {};
  const dayBtns = () => [...document.querySelectorAll('#scDays [data-k]')];
  for (const k of [0, 1, 2, 9]) {
    const b = dayBtns().find(x => x.dataset.k == k); if (!b) continue; b.click(); await w(120);
    out.scanners['d' + k] = [...document.querySelectorAll('#scCards .scard')].map(c => txt(c.querySelector('.top'))).join(' | ');
  }
  dayBtns()[0]?.click(); await w(100);

  await go('#daily');
  out.daily = { lead: txt($('dyLead')), inout: txt($('dyInOut')), nh: txt($('dyNH')), idx: txt($('dyIdx')),
    breakouts: document.querySelectorAll('#boTb tr').length };

  // open a chart three times: height must not grow
  await go('#leaders');
  const hs = [];
  for (let i = 0; i < 3; i++) {
    document.querySelector('#tb tr').click(); await w(500);
    hs.push($('cPrice').clientHeight + '/' + $('cVol').clientHeight);
    $('dClose').click(); await w(150);
  }
  out.chartHeights = hs;
  return out;
})();
