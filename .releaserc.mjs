const commitPartial = `*{{#if scope}} **{{scope}}:**
{{~/if}} {{#if subject}}
  {{~subject}}
{{~else}}
  {{~header}}
{{~/if}}

{{~!-- commit link --}}{{~#if hash}} {{#if @root.linkReferences~}}
  ([{{shortHash}}]({{commitUrlFormat}}))
{{~else}}
  {{~shortHash}}
{{~/if}}{{~/if}}

{{~!-- commit references --}}
{{~#if references~}}
  , closes
  {{~#each references}} {{#if @root.linkReferences~}}
    [
    {{~#if this.owner}}
      {{~this.owner}}/
    {{~/if}}
    {{~this.repository}}{{this.prefix}}{{this.issue}}]({{issueUrlFormat}})
  {{~else}}
    {{~#if this.owner}}
      {{~this.owner}}/
    {{~/if}}
    {{~this.repository}}{{this.prefix}}{{this.issue}}
  {{~/if}}{{/each}}
{{~/if}}

{{#each bodyLines}}
  &nbsp;&nbsp;&nbsp;&nbsp;{{this}}
{{/each}}`

/**
 * Adds the commit body line by line so I can add it with the correct indentation in `changelog-template-commit.hbs`.
 */
function finalizeContext(context) {
	console.log(context)
	for (const commitGroup of context.commitGroups) {
		for (const commit of commitGroup.commits) {
			commit.bodyLines = commit.body?.split('\n').filter((line) => line !== '') ?? []
		}
	}

	return context
}

export default {
	plugins: [
		['@semantic-release/commit-analyzer', {
			preset: 'conventionalcommits',
		}],
		['@semantic-release/release-notes-generator', {
			preset: 'conventionalcommits',
			writerOpts: {
				commitPartial,
				finalizeContext,
			},
		}],
		['@semantic-release/exec', {
			verifyReleaseCmd: 'echo ${nextRelease.version} > .VERSION'
		}],
		['@semantic-release/gitlab', {
			assets: ['docker-compose.yml']
		}],
	],
}
