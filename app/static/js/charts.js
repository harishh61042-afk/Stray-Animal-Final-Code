/* PawConnect charts - draws every <canvas data-pc-chart='{...}'> with Chart.js (loaded before this file).

   Config (JSON):
     type      "bar" | "hbar" | "line" | "doughnut" | "pie"
     labels    ["Jan", "Feb", ...]
     datasets  [{"label": "Reports", "data": [1, 2, 3], "color": "#1f9d63"}]      (doughnut/pie: "colors": [...] optional)
     stacked   true            (bar/hbar)
     legend    true | false    (default: shown for doughnut/pie and for several datasets)
     unit      "%"             (appended to tooltip values)
     center    {"text": "128", "title": "Total"}   (doughnut centre label)
     integer   false           (allow decimals on the value axis; default true)
*/
(function () {
  'use strict';

  var PALETTE = ['#1f9d63', '#0ea5a4', '#f59f00', '#3b82f6', '#8b5cf6', '#e5484d', '#ec4899', '#64748b'];
  var FONT = '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  var live = [];

  function cssVar(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function colors() {
    return {
      text: cssVar('--pc-muted', '#637468'),
      strong: cssVar('--pc-text', '#12241b'),
      grid: cssVar('--pc-border', '#e2eae5'),
      surface: cssVar('--pc-surface', '#ffffff')
    };
  }

  function withAlpha(hex, alpha) {
    var m = /^#([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) { return hex; }
    var n = parseInt(m[1], 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
  }

  function gradient(base, fromAlpha, toAlpha) {
    return function (context) {
      var chart = context.chart;
      var area = chart.chartArea;
      if (!area) { return base; }
      var g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
      g.addColorStop(0, withAlpha(base, fromAlpha));
      g.addColorStop(1, withAlpha(base, toAlpha));
      return g;
    };
  }

  function showMessage(canvas, icon, text) {
    var box = canvas.parentElement;
    var message = box.querySelector('.pc-chart-fallback');
    canvas.hidden = true;
    if (message) {
      message.innerHTML = '<i class="bi ' + icon + '"></i>';
      message.appendChild(document.createTextNode(' ' + text));
      message.hidden = false;
    }
  }

  function isEmpty(cfg) {
    return !(cfg.datasets || []).some(function (set) {
      return (set.data || []).some(function (v) { return Number(v) > 0; });
    });
  }

  var centerPlugin = {
    id: 'pcCenter',
    afterDraw: function (chart, args, opts) {
      if (!opts || !opts.text) { return; }
      var meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data || !meta.data[0]) { return; }
      var ctx = chart.ctx;
      var x = meta.data[0].x;
      var y = meta.data[0].y;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = opts.color;
      ctx.font = '700 28px ' + FONT;
      ctx.fillText(String(opts.text), x, y - (opts.title ? 9 : 0));
      if (opts.title) {
        ctx.fillStyle = opts.muted;
        ctx.font = '500 12px ' + FONT;
        ctx.fillText(String(opts.title), x, y + 17);
      }
      ctx.restore();
    }
  };

  function build(canvas, cfg) {
    var theme = colors();
    var type = cfg.type || 'bar';
    var round = type === 'doughnut' || type === 'pie';
    var horizontal = type === 'hbar';
    var chartType = horizontal ? 'bar' : (type === 'pie' ? 'pie' : type);
    var datasets = (cfg.datasets || []).map(function (set, index) {
      var base = set.color || PALETTE[index % PALETTE.length];
      var out = { label: set.label || '', data: set.data || [] };
      if (round) {
        var slice = (set.colors && set.colors.length) ? set.colors : out.data.map(function (_, i) { return PALETTE[i % PALETTE.length]; });
        out.backgroundColor = slice;
        out.borderWidth = 0;
        out.spacing = type === 'doughnut' ? 3 : 0;
        out.hoverOffset = 6;
      } else if (type === 'line') {
        out.borderColor = base;
        out.borderWidth = 2.5;
        out.tension = 0.35;
        out.fill = (cfg.datasets || []).length === 1;
        out.backgroundColor = gradient(base, 0.28, 0.02);
        out.pointRadius = 0;
        out.pointHoverRadius = 5;
        out.pointBackgroundColor = base;
      } else {
        var single = (cfg.datasets || []).length === 1 && !cfg.stacked;
        out.backgroundColor = single ? (set.colors && set.colors.length ? set.colors : gradient(base, 1, 0.45)) : base;
        out.borderRadius = 8;
        out.borderSkipped = false;
        out.maxBarThickness = horizontal ? 22 : 34;
      }
      return out;
    });

    var showLegend = cfg.legend !== undefined ? !!cfg.legend : (round || datasets.length > 1);
    var options = {
      responsive: true,
      maintainAspectRatio: false,
      animation: window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 600 },
      interaction: { mode: round ? 'nearest' : 'index', intersect: round },
      plugins: {
        legend: {
          display: showLegend,
          position: round ? 'bottom' : 'top',
          align: round ? 'center' : 'end',
          labels: { color: theme.text, usePointStyle: true, pointStyle: 'circle', boxWidth: 8, boxHeight: 8, padding: 16, font: { family: FONT, size: 12 } }
        },
        tooltip: {
          backgroundColor: 'rgba(15, 36, 27, .94)', titleColor: '#fff', bodyColor: '#e6f0ea', padding: 12, cornerRadius: 12,
          displayColors: true, boxPadding: 4, titleFont: { family: FONT, weight: '600' }, bodyFont: { family: FONT },
          callbacks: cfg.unit ? { label: function (item) { return ' ' + (item.dataset.label ? item.dataset.label + ': ' : item.label + ': ') + item.formattedValue + cfg.unit; } } : {}
        },
        pcCenter: round && cfg.center ? { text: cfg.center.text, title: cfg.center.title, color: theme.strong, muted: theme.text } : false
      }
    };

    if (round) {
      if (type === 'doughnut') { options.cutout = '72%'; }
    } else {
      var valueAxis = {
        beginAtZero: true,
        stacked: !!cfg.stacked,
        grid: { color: theme.grid, borderDash: [4, 4] },
        border: { display: false },
        ticks: { color: theme.text, precision: cfg.integer === false ? undefined : 0, font: { family: FONT, size: 11 }, padding: 8 }
      };
      if (cfg.max) { valueAxis.max = cfg.max; }
      var categoryAxis = {
        stacked: !!cfg.stacked,
        grid: { display: false },
        border: { display: false },
        ticks: { color: theme.text, font: { family: FONT, size: 11 }, maxRotation: 0, autoSkipPadding: 12 }
      };
      options.indexAxis = horizontal ? 'y' : 'x';
      options.scales = horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis };
    }

    return new window.Chart(canvas.getContext('2d'), {
      type: chartType,
      data: { labels: cfg.labels || [], datasets: datasets },
      options: options,
      plugins: [centerPlugin]
    });
  }

  function draw(canvas) {
    var cfg;
    try {
      cfg = JSON.parse(canvas.getAttribute('data-pc-chart'));
    } catch (e) {
      showMessage(canvas, 'bi-exclamation-circle', 'This chart could not be displayed.');
      return;
    }
    if (typeof window.Chart === 'undefined') {
      showMessage(canvas, 'bi-bar-chart', 'Chart could not be loaded (check your internet connection). The numbers are still listed on this page.');
      return;
    }
    if (isEmpty(cfg)) {
      showMessage(canvas, 'bi-bar-chart', 'No data to show yet.');
      return;
    }
    try {
      live.push({ canvas: canvas, cfg: cfg, chart: build(canvas, cfg) });
    } catch (e) {
      showMessage(canvas, 'bi-exclamation-circle', 'This chart could not be displayed.');
    }
  }

  function drawAll() {
    Array.prototype.slice.call(document.querySelectorAll('canvas[data-pc-chart]')).forEach(function (canvas) {
      if (!live.some(function (item) { return item.canvas === canvas; })) { draw(canvas); }
    });
  }

  // Re-draw with the right colours when the theme is switched.
  window.addEventListener('pc:theme', function () {
    live.forEach(function (item) {
      item.chart.destroy();
      item.chart = build(item.canvas, item.cfg);
    });
  });

  window.PawCharts = { render: drawAll };
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', drawAll); } else { drawAll(); }
})();
