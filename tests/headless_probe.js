// Appended to the page by run_headless.sh. Exercises every tab and filter, then writes
// the results (and any uncaught errors) into <pre id="probe">.
(function () {
  const errors = [];
  window.addEventListener('error', e => errors.push(String(e.message)));
  window.addEventListener('unhandledrejection', e => errors.push('promise: ' + String(e.reason)));
  const w = ms => new Promise(r => setTimeout(r, ms));
  const $ = id => document.getElementById(id);
  const txt = el => (el ? el.innerText.replace(/\s+/g, ' ').trim() : null);
  const nums = sel => [...document.querySelectorAll(sel)].map(x => x.innerText).join(',');
  const go = async h => { location.hash = h; await w(300); };
  setTimeout(async () => {
    const o = {};
    try {
      await go('#leaders');
      o.leaders = [txt($('sLeaders')), txt($('sIdx')), txt($('sNH')), txt($('sSec'))].join(' ; ');
      o.firstRow = txt(document.querySelector('#tb tr'))?.split(' ').slice(0, 2).join(' ');
      o.filters = {};
      for (const f of ['nh', 'nearma', 'setup']) {
        const b = document.querySelector(`[data-f="${f}"]`); b.click(); await w(60);
        o.filters[f] = document.querySelectorAll('#tb tr').length; b.click(); await w(60);
      }
      await go('#strategies');
      o.strategies = [...document.querySelectorAll('#stCards .scard')].map(c => txt(c.querySelector('.top')));
      o.scorecard = [...document.querySelectorAll('#scTb tr')].map(txt);
      await go('#scanners');
      o.scanDaily = {};
      for (const k of [0, 1, 2, 9]) {
        document.querySelector(`#scDays [data-k="${k}"]`).click(); await w(100);
        o.scanDaily['d' + k] = nums('#scCards .num');
      }
      document.querySelector('#scDays [data-k="0"]').click(); await w(80);
      document.querySelector('#scTf [data-v="w"]').click(); await w(2500);
      o.scanWeekly = {};
      for (const k of [0, 1, 2, 7]) {
        document.querySelector(`#scDays [data-k="${k}"]`)?.click(); await w(150);
        o.scanWeekly['w' + k] = txt(document.querySelector(`#scDays [data-k="${k}"]`)) + ' : ' + nums('#scCards .num');
      }
      o.weeklyHead = [...document.querySelectorAll('#scHead th')].map(x => x.innerText).slice(2, 7).join('|');
      document.querySelector('#scTf [data-v="d"]').click(); await w(150);
      o.dailyHeadBack = [...document.querySelectorAll('#scHead th')].map(x => x.innerText).slice(2, 7).join('|');
      o.scanDailyAgain = nums('#scCards .num');
      await go('#daily');
      o.daily = [txt($('dyLead')), txt($('dyInOut')), txt($('dyNH')), txt($('dyIdx')), document.querySelectorAll('#boTb tr').length].join(' ; ');
      o.weeklyReview = [txt($('wrTitle')), txt($('wrIdx')), txt($('wrLead')), txt($('wrInOut')), txt($('wrBo')), txt($('wrBoN'))].join(' ; ');
      o.wrWeeks = nums('#wrWeeks button');
      document.querySelector('#wrWeeks [data-k="1"]')?.click(); await w(200);
      o.weeklyReviewPrev = [txt($('wrTitle')), txt($('wrLead')), txt($('wrInOut')), txt($('wrBo'))].join(' ; ');
      o.wrLists = ['wrIn', 'wrOut', 'wrUp', 'wrDn', 'wrBoList'].map(id => id + ':' + document.querySelectorAll('#' + id + ' tr').length).join(' ');
    } catch (e) { errors.push('probe: ' + e.message); }
    o.errors = errors;
    const pre = document.createElement('pre'); pre.id = 'probe'; pre.textContent = JSON.stringify(o, null, 1);
    document.body.appendChild(pre);
  }, 3000);
})();
