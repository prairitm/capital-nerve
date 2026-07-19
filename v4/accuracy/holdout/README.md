# Locked holdout

This directory is excluded from normal development replay. The manifest reserves ten companies/layouts that were not used to tune the parser. Source retrieval, draft labeling, and independent approval remain assigned to a separate human reviewer.

Do not place holdout predictions in development reports. Run the holdout evaluator with the explicit release flag only after every manifest entry has an immutable document ID and every label in holdout/gold is approved.

No holdout result exists in this change.
