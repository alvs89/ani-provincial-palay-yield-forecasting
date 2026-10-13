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
  if (state.page === 'result' || state.page === 'forecast') render();
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
      <p class="environmentSeparation">Environmental Decision Support is a separate short-term analysis and does not alter the XGBoost yield estimate.</p>
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
        <article class="environmentDecisionCard"><span>Environmental Outlook Coverage</span><strong>${environmentalEscape(context.location || 'Unavailable')} · ${environmentalEscape(context.ecosystem || 'Unavailable')}</strong></article>
        <article class="environmentDecisionCard"><span>Selected model context</span><strong>${environmentalEscape(forecast?.province || 'Unavailable')} · ${environmentalEscape(forecast?.ecosystem || 'Unavailable')}</strong></article>
      </div>
      <p class="environmentSeparation">Environmental Decision Support is a separate short-term analysis and does not alter the XGBoost yield estimate.</p>
    </section>`;
  }

  const window = context.forecast_window || {};
  const freshness = report.freshness || {};
  const freshnessStatus = String(freshness.status || 'UNKNOWN').toUpperCase();
  const isDecisionCurrent = report.currentForDecisionSupport === true
    && ['UPCOMING', 'CURRENT'].includes(freshnessStatus);
  const coveredPeriod = environmentalEscape(environmentalWindow(window));
  const architectureText = 'Environmental Decision Support is a separate short-term analysis and does not alter the XGBoost yield estimate.';
  if (!isDecisionCurrent) {
    const statusMessage = freshnessStatus === 'EXPIRED'
      ? 'Environmental outlook expired.'
      : 'Environmental outlook currency could not be verified.';
    const explanation = freshnessStatus === 'EXPIRED'
      ? `The stored outlook covers ${coveredPeriod}. A current environmental outlook is required before this information can be used for planning.`
      : 'The stored outlook cannot be presented as current decision-support information.';
    return `<section class="environmentPanel" aria-labelledby="environmentSupportTitle">
      <div class="environmentHeader"><div><span class="eyebrow">SEPARATE ENVIRONMENTAL ANALYSIS</span><h2 id="environmentSupportTitle">Environmental Decision Support</h2></div></div>
      <div class="environmentUnavailable"><strong>${statusMessage}</strong><p>Covered period: ${coveredPeriod}</p><p>${explanation}</p></div>
      <p class="environmentSeparation">${architectureText}</p>
    </section>`;
  }
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
  const soilSeries = siteVerified ? site.soil_context?.soil_series : null;
  const siteText = siteVerified
    ? `Verified site context${soilSeries ? `: ${environmentalEscape(soilSeries)}` : ''}`
    : 'Field-specific soil and establishment information has not been verified for this assessment.';
  const siteStatus = siteVerified ? 'Verified' : 'Field Context Not Verified';
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
  const conclusion = decision.conclusion || 'No environmental interpretation is available for this outlook.';
  const cautionText = waterAvailability === 'Caution'
    ? 'Forecast rainfall is below the reference atmospheric and crop-water demand indicators for the assessed period.'
    : 'This environmental assessment is contextual and does not issue a planting recommendation.';
  const withheldText = 'ANI does not issue a planting recommendation because effective rainfall, verified field soil conditions, antecedent root-zone water storage, and locally validated decision thresholds are not yet available.';

  return `<section class="environmentPanel" aria-labelledby="environmentSupportTitle">
    <div class="environmentHeader">
      <div>
        <span class="eyebrow">SEPARATE ENVIRONMENTAL ANALYSIS</span>
        <h2 id="environmentSupportTitle">Environmental Decision Support</h2>
        <p>Short-term environmental context for agricultural planning.</p>
      </div>
      <div class="environmentWindow"><span>${freshnessStatus === 'UPCOMING' ? 'Upcoming Environmental Outlook' : 'Current Environmental Outlook'}</span><strong>${coveredPeriod}</strong><small>${environmentalEscape(context.location || '')} · ${environmentalEscape(context.ecosystem || '')}</small></div>
    </div>
    ${forecast?.yieldUnavailable ? '<div class="infoBox"><strong>Yield estimate:</strong> Unavailable - historical/model input requirements are not satisfied. <strong>Environmental outlook:</strong> Available for this selection as a separate short-term environmental outlook.</div>' : ''}
    <p class="environmentSeparation">${architectureText}</p>
    <div class="environmentStatus"><div><span>Water-Balance Signal</span><strong>${environmentalEscape(waterAvailability)}</strong></div><p>${environmentalEscape(cautionText)}</p><small>Atmospheric Water Balance: ${environmentalEscape(atmosphericStatus)}</small></div>
    <div class="environmentMetrics">
      <div class="environmentMetric"><span>Forecast Rainfall</span><strong>${rainfall} mm</strong></div>
      <div class="environmentMetric"><span>FAO-56 Reference ET₀</span><strong>${et0} mm</strong></div>
      <div class="environmentMetric"><span>Climatic Water Balance (P − ET₀)</span><strong>${pMinusEt0}</strong></div>
      <div class="environmentMetric"><span>Rainfall / ET₀</span><strong>${rainfallPercent}</strong></div>
    </div>
    <div class="environmentScenario">
      <h3>Reference Crop-Water Scenario</h3>
      <p>Reference sensitivity scenario; not a locally calibrated decision threshold.</p>
      <div class="environmentMetrics environmentScenarioMetrics">
        <div class="environmentMetric"><span>Reference Kc</span><strong>${kc}</strong></div>
        <div class="environmentMetric"><span>Reference ETc Scenario</span><strong>${etc} mm</strong></div>
        <div class="environmentMetric"><span>Best-Case Rainfall − ETc</span><strong>${rainfallMinusEtc}</strong></div>
      </div>
      <p class="environmentFootnote">This reference coefficient supports sensitivity analysis and is not a locally calibrated planting threshold.</p>
    </div>
    <div class="environmentDecisions">
      <article class="environmentDecisionCard"><span>Site Context</span><strong class="${siteVerified ? 'environmentVerified' : 'environmentUnverified'}">${environmentalEscape(siteStatus)}</strong><p>${siteText}</p>${siteVerified ? '' : '<small>Field-specific site information has not been verified for this assessment.</small>'}</article>
      <article class="environmentDecisionCard"><span>Planting Recommendation</span><strong>${environmentalEscape(recommendation)}</strong><p>${environmentalEscape(withheldText)}</p></article>
    </div>
    <article class="environmentInterpretation"><h3>Why?</h3><p>${environmentalEscape(conclusion)}</p><strong>This supports a cautionary water-availability interpretation, not a planting recommendation.</strong></article>
    ${blockers.length ? `<details class="environmentEvidence"><summary>Information Required for Planting Guidance</summary><ul>${blockers.map(item => `<li>${environmentalEscape(item)}</li>`).join('')}</ul></details>` : ''}
  </section>`;
}
