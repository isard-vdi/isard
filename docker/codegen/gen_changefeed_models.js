'use strict';

const { Parser, fromFile, DiagnosticSeverity } = require('@asyncapi/parser');
const { PythonFileGenerator, PYTHON_PYDANTIC_PRESET } = require('@asyncapi/modelina');

async function main() {
	const [,, specPath, outputDir, packageName] = process.argv;
	if (!specPath || !outputDir || !packageName) {
		console.error('Usage: node gen_changefeed_models.js <spec.yaml> <output-dir> <packageName>');
		process.exit(2);
	}

	const parser = new Parser();
	const { document, diagnostics } = await fromFile(parser, specPath).parse();

	const errors = diagnostics.filter((d) => d.severity === DiagnosticSeverity.Error);
	if (errors.length > 0 || !document) {
		for (const diag of errors) {
			console.error(`error ${diag.code}: ${diag.message} at ${JSON.stringify(diag.path)}`);
		}
		process.exit(1);
	}

	const generator = new PythonFileGenerator({ presets: [PYTHON_PYDANTIC_PRESET] });
	const models = await generator.generateToFiles(document, outputDir, { packageName });
	console.log(`Generated ${models.length} python models in ${outputDir}`);
}

main().catch((err) => {
	console.error(err);
	process.exit(1);
});
