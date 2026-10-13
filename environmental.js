let environmentalSupport = null;

const environmentalEscape = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}[char]));

function environmentalNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : 'Unavailable';
}

function environmentalSignedMm(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'Unavailable';
  return `${number < 0 ? '−' : ''}${Math.abs(number).toFixed(2)} mm`;
}

function environmentalWindow(window) {
  if (!window?.start || !window?.end) return 'Forecast window unavailable';
  const start = new Date(`${window.start}T12:00:00`);
  const end = new Date(`${window.end}T12:00:00`);
  if (Number.isNaN(start.valueOf()) || Number.isNaN(end.valueOf())) {
    return 'Forecast window unavailable';
  }
  const month = date => date.toLocaleDateString('en-US', { month: 'long' });
  if (start.getFullYear() === end.getFullYear() && start.getMonth() === end.getMonth()) {
    return `${month(start)} ${start.getDate()}–${end.getDate()}, ${end.getFullYear()}`;
  }
  const fullDate = date => date.toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric'
  });
  return `${fullDate(start)}–${fullDate(end)}`;
}

async function loadEnvironmentalDecisionSupport() {
  try {
    const response = await fetch(`${API_BASE}/environmental-decision-support`);
    if (!response.ok) throw new Error('Environmental output unavailable.');
    const payload = await response.json();
    environmentalSupport = payload?.available === true
      ? payload
      : { available: false, message: payload?.message };
  } catch {
    environmentalSupport = { available: false };
  }
  if (state.page === 'result') render();
}

function normalizeEnvironmentalContext(value) {
  return String(value ?? '').trim().toLowerCase();
}

function environmentalDecisionSupport(forecast) {
  if (!environmentalSupport) {
    return `<section class="environmentPanel" aria-labelledby="environmentSupportTitle">
      <h2 id="environmentSupportTitle">Environmental Decision Support</h2>
      <p class="environmentUnavailable">Loading the separate environmental outlook…</p>
    </section>`;
  }
  if (!environmentalSupport.available) {
    return `<section class="environmentPanel" aria-labelledby="environmentSupportTitle">
      <h2 id="environmentSupportTitle">Environmental Decision Support</h2>
      <p class="environmentUnavailable">Environmental decision-support data are not currently available.</p>
    </section>`;
  }

  const report = environmentalSupport;
  const context = report.context || {};
  const forecastProvince = normalizeEnvironmentalContext(forecast?.province);
  const forecastEcosystem = normalizeEnvironmentalContext(forecast?.ecosystem);
  const environmentalProvince = normalizeEnvironmentalContext(context.location);
  const environmentalEcosystem = normalizeEnvironmentalContext(context.ecosystem);
  const contextMatches = forecastProvince === environmentalProvince
    && forecastEcosystem === environmentalEcosystem;

  if (!contextMatches) {
    return `<section class="environmentPanel" aria-labelledby="environmentSupportTitle">
      <div class="environmentHeader"><div>
        <span class="eyebrow">SEPARATE ENVIRONMENTAL ANALYSIS</span>
        <h2 id="environmentSupportTitle">Environmental Decision Support</h2>
      </div></div>
      <p class="environmentUnavailable">Environmental outlook unavailable for this forecast selection.</p>
      <div class="environmentDecisions">
        <article class="environmentDecisionCard"><span>Current environmental decision-support pilot covers</span><strong>${environmentalEscape(context.location || 'Unavailable')} · ${environmentalEscape(context.ecosystem || 'Unavailable')}</strong></article>
        <article class="environmentDecisionCard"><span>Current yield forecast</span><strong>${environmentalEscape(forecast?.province || 'Unavailable')} · ${environmentalEscape(forecast?.ecosystem || 'Unavailable')}</strong></article>
      </div>
      <p class="environmentSeparation">The environmental analysis is kept separate because it does not match the selected province and ecosystem.</p>
    </section>`;
  }

  const window = context.forecast_window || {};
  const water = report.water_balance || {};
  const scenario = report.crop_water_reference_scenario || {};
  const site = report.site_context || {};
  const decision = report.decision_support || {};
  const overallStatus = String(decision.overall_status || '');
  const waterAvailability = overallStatus.includes('CAUTION') ? 'Caution' : 'Review required';
  const atmosphericStatus = water.atmospheric_water_status === 'DEFICIT_SIGNAL'
    ? 'Deficit Signal'
    : water.atmospheric_water_status === 'NO_DEFICIT_SIGNAL' ? 'No Deficit Signal' : 'Not assessed';
  const rainfallRatio = Number(water.rainfall_to_et0_ratio);
  const rainfallPercent = Number.isFinite(rainfallRatio) ? `${(rainfallRatio * 100).toFixed(1)}%` : 'Unavailable';
  const siteVerified = String(site.verification || '').toLowerCase() === 'verified';
  const soilSeries = site.soil_context?.soil_series;
  const siteText = siteVerified
    ? `Verified site context${soilSeries ? `: ${environmentalEscape(soilSeries)}` : ''}`
    : `Test scenario${soilSeries ? `: ${environmentalEscape(soilSeries)}` : ''}`;
  const siteStatus = siteVerified ? 'Verified' : 'TEST / UNVERIFIED';
  const recommendation = decision.planting_recommendation_status === 'WITHHELD'
    ? 'Not issued'
    : decision.planting_recommendation_status === 'ISSUED' ? 'Issued' : 'Status unavailable';
  const rainfall = environmentalNumber(water.forecast_rainfall_mm);
  const et0 = environmentalNumber(water.reference_et0_fao56_mm);
  const pMinusEt0 = environmentalSignedMm(water.p_minus_et0_mm);
  const kc = environmentalNumber(scenario.kc, 2);
  const etc = environmentalNumber(scenario.estimated_etc_mm);
  const rainfallMinusEtc = environmentalSignedMm(scenario.best_case_rainfall_minus_etc_mm);
  const runtimeLabels = {
    establishment_method: 'Establishment method',
    soil_series: 'Verified field soil context',
    effective_rainfall_mm: 'Effective rainfall / crop-water balance'
  };
  const validationLabels = {
    'effective_rainfall_rule.minimum_mm': 'Validated effective-rainfall threshold',
    'soil_water_rule.maximum': 'Validated soil-water maximum',
    'soil_water_rule.minimum': 'Validated soil-water minimum',
    'temperature_rule.maximum_c': 'Validated temperature maximum',
    'temperature_rule.minimum_c': 'Validated temperature minimum',
    'validation_status=VALIDATED': 'Agronomic ruleset validation',
    'wind_rule.maximum_gust_kmh': 'Validated wind-gust threshold'
  };
  const evidenceItems = [
    ...(decision.remaining_runtime_blocks || []).map(item => runtimeLabels[item] || String(item).replaceAll('_', ' ')),
    ...(decision.remaining_validation_blocks || []).map(item => validationLabels[item] || String(item).replaceAll('_', ' '))
  ];
  const blockers = [...new Set(evidenceItems)];
  const conclusion = decision.conclusion || 'Stage 9 did not provide an interpretation for this outlook.';
  const cautionText = waterAvailability === 'Caution'
    ? 'Forecast rainfall is substantially below reference atmospheric and crop-water demand for the assessed period.'
    : 'This environmental assessment is contextual and does not issue a planting recommendation.';
  const withheldText = 'ANI does not issue a planting recommendation because effective rainfall, verified field soil conditions, antecedent root-zone water storage, and locally validated decision thresholds are not yet available.';

  return `<section class="environmentPanel" aria-labelledby="environmentSupportTitle">
    <div class="environmentHeader">
      <div>
        <span class="eyebrow">SEPARATE ENVIRONMENTAL ANALYSIS</span>
        <h2 id="environmentSupportTitle">Environmental Decision Support</h2>
        <p>Short-term environmental context for agricultural planning. This analysis is separate from the trained yield-forecasting model.</p>
      </div>
      <div class="environmentWindow"><span>Current Environmental Outlook</span><strong>${environmentalEscape(environmentalWindow(window))}</strong><small>${environmentalEscape(context.location || '')} · ${environmentalEscape(context.ecosystem || '')}</small></div>
    </div>
    <p class="environmentSeparation">This ${environmentalEscape(environmentalWindow(window))} outlook is independent of the selected quarterly yield target and is not weather used by the XGBoost forecast.</p>
    <div class="environmentStatus"><div><span>Water Availability</span><strong>${environmentalEscape(waterAvailability)}</strong></div><p>${environmentalEscape(cautionText)}</p><small>Atmospheric Water Balance: ${environmentalEscape(atmosphericStatus)}</small></div>
    <div class="environmentMetrics">
      <div class="environmentMetric"><span>Forecast Rainfall</span><strong>${rainfall} mm</strong></div>
      <div class="environmentMetric"><span>FAO-56 Reference ET₀</span><strong>${et0} mm</strong></div>
      <div class="environmentMetric"><span>Climatic Water Balance (P − ET₀)</span><strong>${pMinusEt0}</strong></div>
      <div class="environmentMetric"><span>Rainfall / ET₀</span><strong>${rainfallPercent}</strong></div>
    </div>
    <div class="environmentScenario">
      <h3>Reference Crop-Water Scenario</h3>
      <p>${environmentalEscape(scenario.scenario_label || 'FAO reference sensitivity scenario; not locally validated')}</p>
      <div class="environmentMetrics environmentScenarioMetrics">
        <div class="environmentMetric"><span>Reference Kc</span><strong>${kc}</strong></div>
        <div class="environmentMetric"><span>Reference ETc Scenario</span><strong>${etc} mm</strong></div>
        <div class="environmentMetric"><span>Best-Case Rainfall − ETc</span><strong>${rainfallMinusEtc}</strong></div>
      </div>
      <p class="environmentFootnote">This coefficient is used for sensitivity analysis and is not a locally validated Nueva Ecija rainfed planting threshold.</p>
    </div>
    <div class="environmentDecisions">
      <article class="environmentDecisionCard"><span>Site Context</span><strong class="${siteVerified ? 'environmentVerified' : 'environmentUnverified'}">${environmentalEscape(siteStatus)}</strong><p>${siteText}</p>${siteVerified ? '' : '<small>Site details are test inputs, not verified field information.</small>'}</article>
      <article class="environmentDecisionCard"><span>Planting Recommendation</span><strong>${environmentalEscape(recommendation)}</strong><p>${environmentalEscape(withheldText)}</p></article>
    </div>
    <article class="environmentInterpretation"><h3>Why?</h3><p>${environmentalEscape(conclusion)}</p><strong>This supports a cautionary water-availability interpretation, not a planting recommendation.</strong></article>
    ${blockers.length ? `<details class="environmentEvidence"><summary>Remaining evidence and validation needs</summary><ul>${blockers.map(item => `<li>${environmentalEscape(item)}</li>`).join('')}</ul></details>` : ''}
  </section>`;
}
