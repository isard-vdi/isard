// Contract between the shipped vmalert rules and the metrics the Go collectors
// export.
//
// A rule is plain YAML: a metric or a label that does not exist costs nothing
// at load time, the expression simply never evaluates true, and the alert is
// silently inert forever. This test resolves every exported name the way the
// collectors build it (namespace + subsystem + short name) and fails when a
// rule expression references anything else.
//
// The collector sources are parsed instead of imported: they depend on the
// generated OpenAPI client, which is absent from a clean checkout, and this
// guard has to run wherever the rules do.
package stats

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gopkg.in/yaml.v3"
)

const (
	rulesDir     = "../docker/vmalert/rules"
	collectorDir = "collector"

	// Anchors: the resolver is static, so it has to prove it still understands
	// the two ways a desc is built (the plain BuildFQName call and the local
	// closure) before its "not exported" verdict means anything.
	anchorDirect = "isardvdi_system_cpu_cores"
	anchorHelper = "isardvdi_storage_governor_backlog"
	minMetrics   = 50
)

// labels a scrape target adds, which no collector declares.
var infraLabels = map[string]bool{"job": true, "instance": true, "__name__": true}

type metricDef struct {
	labels      map[string]bool
	labelsKnown bool
}

func (m *metricDef) addLabel(name string) {
	if m.labels == nil {
		m.labels = map[string]bool{}
	}
	m.labels[name] = true
}

func TestVmalertRulesOnlyReferenceExportedMetrics(t *testing.T) {
	exported := exportedMetrics(t)

	require.GreaterOrEqual(t, len(exported), minMetrics,
		"static resolver found too few metrics, it no longer understands the collectors")
	require.Contains(t, exported, anchorDirect)
	require.Contains(t, exported, anchorHelper)

	refs, recorded := ruleReferences(t)
	require.NotEmpty(t, refs, "no metric references found in %s", rulesDir)

	problems := []string{}
	for _, ref := range refs {
		if recorded[ref.name] {
			continue
		}
		def, ok := exported[ref.name]
		if !ok {
			problems = append(problems, fmt.Sprintf(
				"%s: %s references %q, which no collector under stats/ exports",
				ref.file, ref.rule, ref.name))
			continue
		}
		if !def.labelsKnown {
			continue
		}
		for _, label := range ref.labels {
			if def.labels[label] || infraLabels[label] {
				continue
			}
			problems = append(problems, fmt.Sprintf(
				"%s: %s matches on label %q of %q, which carries labels %s",
				ref.file, ref.rule, label, ref.name, sortedKeys(def.labels)))
		}
	}

	sort.Strings(problems)
	assert.Empty(t, problems, "vmalert rules reference metrics or labels that are never exported:\n%s",
		strings.Join(problems, "\n"))
}

// --- rules side -------------------------------------------------------------

type metricRef struct {
	file   string
	rule   string
	name   string
	labels []string
}

// ruleReferences returns every isardvdi_* selector found in an expression or in
// a promtool input series, plus the names the files define themselves through a
// recording rule (those are series only vmalert ever materialises).
func ruleReferences(t *testing.T) ([]metricRef, map[string]bool) {
	t.Helper()

	entries, err := os.ReadDir(rulesDir)
	require.NoError(t, err)

	refs := []metricRef{}
	recorded := map[string]bool{}
	for _, entry := range entries {
		if entry.IsDir() || (!strings.HasSuffix(entry.Name(), ".yml") && !strings.HasSuffix(entry.Name(), ".yaml")) {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(rulesDir, entry.Name()))
		require.NoError(t, err)

		var doc yaml.Node
		require.NoError(t, yaml.Unmarshal(raw, &doc), "parse %s", entry.Name())

		walkRuleNode(&doc, "", func(rule, key, value string) {
			if key == "record" {
				recorded[value] = true
				return
			}
			for _, sel := range selectors(value) {
				sel.file = entry.Name()
				sel.rule = rule
				refs = append(refs, sel)
			}
		})
	}
	return refs, recorded
}

// walkRuleNode calls fn for every expr/series/record scalar, tagged with the
// nearest enclosing alert or record name so a failure names the broken rule.
func walkRuleNode(node *yaml.Node, rule string, fn func(rule, key, value string)) {
	switch node.Kind {
	case yaml.DocumentNode, yaml.SequenceNode:
		for _, child := range node.Content {
			walkRuleNode(child, rule, fn)
		}
	case yaml.MappingNode:
		for i := 0; i+1 < len(node.Content); i += 2 {
			key, value := node.Content[i].Value, node.Content[i+1]
			if value.Kind == yaml.ScalarNode && (key == "alert" || key == "record" || key == "name") {
				rule = value.Value
			}
		}
		for i := 0; i+1 < len(node.Content); i += 2 {
			key, value := node.Content[i].Value, node.Content[i+1]
			if value.Kind == yaml.ScalarNode {
				switch key {
				case "expr", "series", "record":
					fn(rule, key, value.Value)
				}
				continue
			}
			walkRuleNode(value, rule, fn)
		}
	}
}

// selectors pulls every isardvdi_* metric name out of a promql expression (or a
// promtool series line) together with the labels its matcher block filters on.
func selectors(expr string) []metricRef {
	out := []metricRef{}
	for i := 0; i < len(expr); {
		idx := strings.Index(expr[i:], "isardvdi_")
		if idx < 0 {
			break
		}
		start := i + idx
		if start > 0 && isNameByte(expr[start-1]) {
			i = start + len("isardvdi_")
			continue
		}
		end := start
		for end < len(expr) && (isNameByte(expr[end]) || expr[end] == ':') {
			end++
		}
		ref := metricRef{name: expr[start:end]}
		rest := end
		for rest < len(expr) && (expr[rest] == ' ' || expr[rest] == '\t') {
			rest++
		}
		if rest < len(expr) && expr[rest] == '{' {
			block, next := matcherBlock(expr, rest)
			ref.labels = matcherLabels(block)
			rest = next
		}
		out = append(out, ref)
		i = rest
	}
	return out
}

func isNameByte(b byte) bool {
	return b == '_' || (b >= 'a' && b <= 'z') || (b >= 'A' && b <= 'Z') || (b >= '0' && b <= '9')
}

// matcherBlock returns the contents of the {...} starting at open, skipping over
// quoted label values so a brace inside a value never ends it early.
func matcherBlock(expr string, open int) (string, int) {
	quote := byte(0)
	for i := open + 1; i < len(expr); i++ {
		c := expr[i]
		switch {
		case quote != 0:
			if c == '\\' {
				i++
			} else if c == quote {
				quote = 0
			}
		case c == '"' || c == '\'' || c == '`':
			quote = c
		case c == '}':
			return expr[open+1 : i], i + 1
		}
	}
	return expr[open+1:], len(expr)
}

func matcherLabels(block string) []string {
	out := []string{}
	quote := byte(0)
	name := strings.Builder{}
	for i := 0; i < len(block); i++ {
		c := block[i]
		if quote != 0 {
			if c == '\\' {
				i++
			} else if c == quote {
				quote = 0
			}
			continue
		}
		switch {
		case c == '"' || c == '\'' || c == '`':
			quote = c
			name.Reset()
		case isNameByte(c):
			name.WriteByte(c)
		case c == '=' || c == '!':
			if name.Len() > 0 {
				out = append(out, name.String())
			}
			name.Reset()
		default:
			name.Reset()
		}
	}
	return out
}

// --- collector side ---------------------------------------------------------

// exportedMetrics resolves every prometheus desc the collectors build, applying
// BuildFQName exactly as they do: the package namespace, the subsystem the
// collector's String() returns, and the short name at the call site.
func exportedMetrics(t *testing.T) map[string]metricDef {
	t.Helper()

	files := parseCollectors(t)
	namespace, ok := constString(files, "namespace")
	require.True(t, ok, "no namespace constant in %s", collectorDir)
	subsystems := subsystemByType(files)
	require.NotEmpty(t, subsystems, "no collector String() method resolved")

	out := map[string]metricDef{}
	for _, file := range files {
		for _, decl := range file.Decls {
			fn, ok := decl.(*ast.FuncDecl)
			if !ok || fn.Body == nil {
				continue
			}
			collectDescs(t, fn, namespace, subsystems, out)
		}
	}
	return out
}

func parseCollectors(t *testing.T) []*ast.File {
	t.Helper()

	entries, err := os.ReadDir(collectorDir)
	require.NoError(t, err)

	fset := token.NewFileSet()
	files := []*ast.File{}
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !strings.HasSuffix(name, ".go") || strings.HasSuffix(name, "_test.go") {
			continue
		}
		parsed, err := parser.ParseFile(fset, filepath.Join(collectorDir, name), nil, 0)
		require.NoError(t, err, "parse %s", name)
		files = append(files, parsed)
	}
	require.NotEmpty(t, files)
	return files
}

func constString(files []*ast.File, name string) (string, bool) {
	for _, file := range files {
		for _, decl := range file.Decls {
			gen, ok := decl.(*ast.GenDecl)
			if !ok || gen.Tok != token.CONST {
				continue
			}
			for _, spec := range gen.Specs {
				value, ok := spec.(*ast.ValueSpec)
				if !ok || len(value.Names) != 1 || len(value.Values) != 1 || value.Names[0].Name != name {
					continue
				}
				if lit, ok := stringLit(value.Values[0]); ok {
					return lit, true
				}
			}
		}
	}
	return "", false
}

// subsystemByType maps a collector type to the subsystem its String() returns,
// which is the second half of every metric name.
func subsystemByType(files []*ast.File) map[string]string {
	out := map[string]string{}
	for _, file := range files {
		for _, decl := range file.Decls {
			fn, ok := decl.(*ast.FuncDecl)
			if !ok || fn.Recv == nil || fn.Name.Name != "String" || fn.Body == nil || len(fn.Body.List) != 1 {
				continue
			}
			ret, ok := fn.Body.List[0].(*ast.ReturnStmt)
			if !ok || len(ret.Results) != 1 {
				continue
			}
			lit, ok := stringLit(ret.Results[0])
			if !ok || len(fn.Recv.List) != 1 {
				continue
			}
			if name, ok := typeName(fn.Recv.List[0].Type); ok {
				out[name] = lit
			}
		}
	}
	return out
}

// descHelper is a local closure that wraps NewDesc, so the short name and the
// variable labels arrive as arguments at each call site instead of inline.
type descHelper struct {
	subsystem  string
	nameArg    int
	labelArg   int
	labelSplat bool
}

func collectDescs(t *testing.T, fn *ast.FuncDecl, namespace string, subsystems map[string]string, out map[string]metricDef) {
	t.Helper()

	vars := localVarTypes(fn)
	helpers, helperBodies := descHelpers(fn, vars, subsystems)

	inHelper := 0
	ast.Inspect(fn, func(node ast.Node) bool {
		lit, isLit := node.(*ast.FuncLit)
		if isLit && helperBodies[lit] {
			inHelper++
			return true
		}
		call, ok := node.(*ast.CallExpr)
		if !ok {
			return true
		}
		if ident, ok := call.Fun.(*ast.Ident); ok {
			if helper, ok := helpers[ident.Name]; ok {
				addHelperCall(call, helper, namespace, out)
			}
			return true
		}
		if !isSelector(call.Fun, "prometheus", "NewDesc") || inHelper > 0 {
			return true
		}
		name, def, ok := describeNewDesc(call, namespace, subsystems, vars)
		require.True(t, ok, "unresolved prometheus.NewDesc call in %s", fn.Name.Name)
		merge(out, name, def)
		return true
	})
}

// descHelpers finds the closures that build a desc from their own arguments and
// records where the short name and the variable labels sit in their signature.
func descHelpers(fn *ast.FuncDecl, vars map[string]string, subsystems map[string]string) (map[string]descHelper, map[*ast.FuncLit]bool) {
	helpers := map[string]descHelper{}
	bodies := map[*ast.FuncLit]bool{}

	ast.Inspect(fn, func(node ast.Node) bool {
		assign, ok := node.(*ast.AssignStmt)
		if !ok {
			return true
		}
		for i, lhs := range assign.Lhs {
			ident, ok := lhs.(*ast.Ident)
			if !ok || i >= len(assign.Rhs) {
				continue
			}
			lit, ok := assign.Rhs[i].(*ast.FuncLit)
			if !ok {
				continue
			}
			params := flatParams(lit.Type.Params)
			ast.Inspect(lit, func(inner ast.Node) bool {
				call, ok := inner.(*ast.CallExpr)
				if !ok || !isSelector(call.Fun, "prometheus", "NewDesc") || len(call.Args) < 3 {
					return true
				}
				subsystem, nameExpr, ok := parseBuildFQName(call.Args[0], subsystems, vars)
				if !ok {
					return true
				}
				nameIdent, ok := nameExpr.(*ast.Ident)
				if !ok {
					return true
				}
				helper := descHelper{subsystem: subsystem, nameArg: -1, labelArg: -1}
				for idx, param := range params {
					if param.name == nameIdent.Name {
						helper.nameArg = idx
					}
					if labelIdent, ok := call.Args[2].(*ast.Ident); ok && param.name == labelIdent.Name {
						helper.labelArg = idx
						helper.labelSplat = param.splat
					}
				}
				if helper.nameArg >= 0 {
					helpers[ident.Name] = helper
					bodies[lit] = true
				}
				return true
			})
		}
		return true
	})
	return helpers, bodies
}

func addHelperCall(call *ast.CallExpr, helper descHelper, namespace string, out map[string]metricDef) {
	if helper.nameArg >= len(call.Args) {
		return
	}
	name, ok := stringLit(call.Args[helper.nameArg])
	if !ok {
		return
	}
	def := metricDef{labelsKnown: helper.labelArg >= 0 && helper.labelSplat}
	if def.labelsKnown {
		for _, arg := range call.Args[helper.labelArg:] {
			label, ok := stringLit(arg)
			if !ok {
				def.labelsKnown = false
				break
			}
			def.addLabel(label)
		}
	}
	merge(out, prometheusName(namespace, helper.subsystem, name), def)
}

func describeNewDesc(call *ast.CallExpr, namespace string, subsystems, vars map[string]string) (string, metricDef, bool) {
	if len(call.Args) < 4 {
		return "", metricDef{}, false
	}
	subsystem, nameExpr, ok := parseBuildFQName(call.Args[0], subsystems, vars)
	if !ok {
		return "", metricDef{}, false
	}
	name, ok := stringLit(nameExpr)
	if !ok {
		return "", metricDef{}, false
	}
	def := metricDef{labelsKnown: true}
	for _, arg := range compositeElements(call.Args[2]) {
		label, ok := stringLit(arg)
		if !ok {
			def.labelsKnown = false
			break
		}
		def.addLabel(label)
	}
	for _, arg := range compositeElements(call.Args[3]) {
		pair, ok := arg.(*ast.KeyValueExpr)
		if !ok {
			def.labelsKnown = false
			break
		}
		label, ok := stringLit(pair.Key)
		if !ok {
			def.labelsKnown = false
			break
		}
		def.addLabel(label)
	}
	return prometheusName(namespace, subsystem, name), def, true
}

// parseBuildFQName unwraps prometheus.BuildFQName(namespace, x.String(), name)
// into the subsystem the receiver reports and the expression naming the metric.
func parseBuildFQName(expr ast.Expr, subsystems, vars map[string]string) (string, ast.Expr, bool) {
	call, ok := expr.(*ast.CallExpr)
	if !ok || !isSelector(call.Fun, "prometheus", "BuildFQName") || len(call.Args) != 3 {
		return "", nil, false
	}
	inner, ok := call.Args[1].(*ast.CallExpr)
	if !ok {
		return "", nil, false
	}
	sel, ok := inner.Fun.(*ast.SelectorExpr)
	if !ok || sel.Sel.Name != "String" {
		return "", nil, false
	}
	recv, ok := sel.X.(*ast.Ident)
	if !ok {
		return "", nil, false
	}
	subsystem, ok := subsystems[vars[recv.Name]]
	if !ok {
		return "", nil, false
	}
	return subsystem, call.Args[2], true
}

// localVarTypes maps a local variable to the struct type it is assigned, which
// is how a receiver expression resolves back to a collector.
func localVarTypes(fn *ast.FuncDecl) map[string]string {
	out := map[string]string{}
	if fn.Recv != nil && len(fn.Recv.List) == 1 && len(fn.Recv.List[0].Names) == 1 {
		if name, ok := typeName(fn.Recv.List[0].Type); ok {
			out[fn.Recv.List[0].Names[0].Name] = name
		}
	}
	ast.Inspect(fn, func(node ast.Node) bool {
		assign, ok := node.(*ast.AssignStmt)
		if !ok {
			return true
		}
		for i, lhs := range assign.Lhs {
			ident, ok := lhs.(*ast.Ident)
			if !ok || i >= len(assign.Rhs) {
				continue
			}
			rhs := assign.Rhs[i]
			if unary, ok := rhs.(*ast.UnaryExpr); ok {
				rhs = unary.X
			}
			composite, ok := rhs.(*ast.CompositeLit)
			if !ok {
				continue
			}
			if name, ok := typeName(composite.Type); ok {
				out[ident.Name] = name
			}
		}
		return true
	})
	return out
}

type param struct {
	name  string
	splat bool
}

func flatParams(fields *ast.FieldList) []param {
	out := []param{}
	if fields == nil {
		return out
	}
	for _, field := range fields.List {
		_, splat := field.Type.(*ast.Ellipsis)
		for _, name := range field.Names {
			out = append(out, param{name: name.Name, splat: splat})
		}
	}
	return out
}

func compositeElements(expr ast.Expr) []ast.Expr {
	composite, ok := expr.(*ast.CompositeLit)
	if !ok {
		return nil
	}
	return composite.Elts
}

func isSelector(expr ast.Expr, pkg, name string) bool {
	sel, ok := expr.(*ast.SelectorExpr)
	if !ok || sel.Sel.Name != name {
		return false
	}
	ident, ok := sel.X.(*ast.Ident)
	return ok && ident.Name == pkg
}

func typeName(expr ast.Expr) (string, bool) {
	if star, ok := expr.(*ast.StarExpr); ok {
		expr = star.X
	}
	ident, ok := expr.(*ast.Ident)
	if !ok {
		return "", false
	}
	return ident.Name, true
}

func stringLit(expr ast.Expr) (string, bool) {
	lit, ok := expr.(*ast.BasicLit)
	if !ok || lit.Kind != token.STRING {
		return "", false
	}
	value, err := strconv.Unquote(lit.Value)
	if err != nil {
		return "", false
	}
	return value, true
}

func prometheusName(parts ...string) string {
	kept := []string{}
	for _, part := range parts {
		if part != "" {
			kept = append(kept, part)
		}
	}
	return strings.Join(kept, "_")
}

func merge(out map[string]metricDef, name string, def metricDef) {
	existing, ok := out[name]
	if !ok {
		out[name] = def
		return
	}
	for label := range def.labels {
		existing.addLabel(label)
	}
	existing.labelsKnown = existing.labelsKnown && def.labelsKnown
	out[name] = existing
}

func sortedKeys(in map[string]bool) []string {
	out := make([]string, 0, len(in))
	for key := range in {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}
