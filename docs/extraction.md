# Preparation and extraction

Preparation supports HTML, PDF, JSON, CSV and plain text. It creates bounded
chunks, section/table metadata, links and an EvidenceLocator for each chunk.
PDF locators preserve page numbers and exact page offsets; HTML locators preserve
stable selector ancestry and chunk offsets; JSON/text uses root fragments and
exact text ranges.

Extraction profiles are versioned data. A profile carries expected ontology
concepts, output schema, validation rules, AI strategy and prompt version. The
AI context has three explicit trusted inputs and one untrusted channel:

1. trusted profile instructions;
2. the complete Core ontology snapshot (object types, properties, relations and
   Rule DSL schema);
3. provider output schema;
4. untrusted source document data and locators.

The provider returns a strict `LLMExtractionPayload` containing entities, facts,
relations, rules, unknown concepts, changes, per-candidate confidence and
evidence. The adapter then creates the full `ExtractionResult` metadata
locally: identifiers, provider/model, UTC timestamp, duration, token usage and
fingerprints. The input fingerprint is derived from the artifact, prepared
document, profile, ontology, prompt, provider and model; the output fingerprint
is derived from canonical semantic JSON and contains no timestamp. The result
is stored as an extraction result and candidate rows; it is not a Fact or Rule
in Core.

The structured-output JSON Schema is generated from
`LLMExtractionPayload.model_json_schema()`, so its required fields and
properties cannot drift apart. `AI_STRUCTURED_OUTPUT_MODE=json_schema` sends a
provider-native JSON Schema request; `json_object` sends the generic JSON mode
and applies the same local contract validation.

The default MockAI is deterministic and supports the BMSTU program/regulation
fixtures. StructuredJsonHttpAIAdapter is an optional provider-neutral adapter
for a configured structured JSON endpoint. A Jev or another model can implement
DocumentUnderstandingPort without changing application/domain code.
