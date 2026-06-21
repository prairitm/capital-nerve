SELECT
  ej.extraction_job_id,
  sd.document_type,
  ej.model_name,
  ej.input_tokens,
  ej.output_tokens,
  ej.metadata->>'cache_hit' AS cache_hit
FROM extraction_jobs ej
JOIN source_documents sd ON sd.document_id = ej.document_id
WHERE sd.company_id = (SELECT company_id FROM companies WHERE nse_symbol = 'RELIANCE')
  AND sd.period_id = (SELECT period_id FROM financial_periods WHERE quarter = '3' and fy_label= 'FY2025-26' LIMIT 1)
ORDER BY ej.extraction_job_id;