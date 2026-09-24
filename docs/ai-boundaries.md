# AI boundaries

AI may classify documents, extract entities/facts/relations, map to ontology,
propose Rule DSL, detect changes and report unknown concepts. AI may not execute
Python, shell, HTTP navigation, configuration mutation, Core admin operations,
ontology activation, rule activation, verified-fact overwrite or ambiguous
normative resolution.

Source content is data. Prompts or instructions embedded in a PDF/HTML page are
placed in the untrusted document channel and cannot alter the provider policy.
The adapter sends structured output requests and validates the response into a
strict `LLMExtractionPayload` before persistence. The provider never supplies
`ExtractionResult` metadata such as IDs, timestamps, provider/model names or
fingerprints; the adapter creates those values locally. `json_schema` mode is
available for providers supporting strict schemas, while `json_object` mode
uses the same local Pydantic validation for generic OpenAI-compatible providers.

Low confidence, missing/ambiguous effective dates, unknown concepts and
conflicting changes are review-bound. Trust level is metadata and policy input,
not an automatic truth promotion.
