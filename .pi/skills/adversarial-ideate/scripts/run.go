package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"
)

type lens struct {
	File  string
	Name  string
	Start string
	End   string
}

var lenses = []lens{
	{"reality", "Reality Tester", "## 1. Reality Tester", "## 2. Prior Art Hunter"},
	{"prior-art", "Prior Art Hunter", "## 2. Prior Art Hunter", "## 3. Devil's Advocate"},
	{"devil", "Devil's Advocate", "## 3. Devil's Advocate", "## 4. Software Materializer"},
	{"materializer", "Software Materializer", "## 4. Software Materializer", "## 5. Depth Probe"},
	{"depth", "Depth Probe", "## 5. Depth Probe", "## Output Discipline"},
}

func main() {
	if _, err := exec.LookPath("codex"); err != nil {
		fatal("codex executable not found on PATH")
	}

	seed := seedFromArgsOrStdin()
	skillDir := mustSkillDir()
	root := workspaceRoot(skillDir)

	lensDoc := mustRead(filepath.Join(skillDir, "references", "reviewer-lenses.md"))
	promptDoc := mustRead(filepath.Join(skillDir, "references", "reviewer-prompt.md"))
	verdictDoc := mustRead(filepath.Join(skillDir, "references", "verdict-format.md"))
	concerns := readOptional(filepath.Join(root, "CURRENT_CONCERNS.md"))

	outputDiscipline := extractSection(lensDoc, "## Output Discipline", "## Source Prompt")
	instructions := extractSection(promptDoc, "## Instructions", "")

	reviewDir, err := os.MkdirTemp("/tmp", "adversarial-ideate.*")
	if err != nil {
		fatal("create review dir: %v", err)
	}
	mustWrite(filepath.Join(reviewDir, "seed.md"), seed+"\n")
	if strings.TrimSpace(concerns) != "" {
		mustWrite(filepath.Join(reviewDir, "current-concerns.md"), concerns+"\n")
	}

	frame := "- Domain hint: workflow / agent tooling\n- What useful means here: both"
	if strings.TrimSpace(concerns) != "" {
		frame += "\n- Current concerns: see CURRENT_CONCERNS.md"
	}

	for _, l := range lenses {
		lensText := extractSection(lensDoc, l.Start, l.End)
		prompt := fmt.Sprintf(`## Seed
%s

## Frame
%s

## Current Concerns
%s

## Your Lens: %s
%s

## Output Discipline
%s

## Instructions
%s
`, seed, frame, nonEmpty(concerns, "(none)"), l.Name, lensText, outputDiscipline, instructions)

		outPath := filepath.Join(reviewDir, l.File+".md")
		fmt.Fprintf(os.Stderr, "[adversarial-ideate] running %s -> %s\n", l.File, outPath)
		cmd := exec.Command("codex", "exec", "--skip-git-repo-check", "-o", outPath, prompt)
		cmd.Stdout = io.Discard
		cmd.Stderr = io.Discard
		if err := cmd.Run(); err != nil {
			fatal("run reviewer %s: %v", l.File, err)
		}
	}

	missing := verifyOutputs(reviewDir)
	fmt.Println("reviewer_cli=codex")
	fmt.Println("REVIEW_DIR=" + reviewDir)
	fmt.Println("SEED_SLUG=" + slugify(seed))
	fmt.Println("DATE=" + time.Now().Format("2006-01-02"))
	fmt.Println("FILES: reality.md prior-art.md devil.md materializer.md depth.md")
	if strings.TrimSpace(concerns) != "" {
		fmt.Println("CURRENT_CONCERNS=loaded")
	} else {
		fmt.Println("CURRENT_CONCERNS=none")
	}
	if len(missing) > 0 {
		fmt.Println("MISSING_OR_EMPTY=" + strings.Join(missing, ","))
		os.Exit(2)
	}
	fmt.Println("VERIFIED=all reviewer outputs exist and are non-empty")
	firstLine := strings.Split(strings.TrimSpace(verdictDoc), "\n")[0]
	fmt.Println("SUGGESTED_VERDICT_TEMPLATE=" + firstLine)
}

func seedFromArgsOrStdin() string {
	if len(os.Args) > 1 {
		seed := strings.TrimSpace(strings.Join(os.Args[1:], " "))
		if seed != "" {
			return seed
		}
	}
	b, _ := io.ReadAll(bufio.NewReader(os.Stdin))
	seed := strings.TrimSpace(string(b))
	if seed == "" {
		fatal("usage: go run ./scripts/run.go <seed>\n(or pipe seed on stdin)")
	}
	return seed
}

func mustSkillDir() string {
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		fatal("cannot locate source file")
	}
	return filepath.Clean(filepath.Dir(filepath.Dir(source)))
}

func workspaceRoot(skillDir string) string {
	root := filepath.Clean(filepath.Join(skillDir, "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "CURRENT_CONCERNS.md")); err == nil {
		return root
	}
	return root
}

func extractSection(text, start, end string) string {
	lines := strings.Split(text, "\n")
	startIdx := -1
	for i, line := range lines {
		if strings.TrimSpace(line) == start {
			startIdx = i
			break
		}
	}
	if startIdx < 0 {
		fatal("failed to extract section: %s", start)
	}
	var body []string
	for _, line := range lines[startIdx+1:] {
		trimmed := strings.TrimSpace(line)
		if end != "" && trimmed == end {
			break
		}
		if end == "" && strings.HasPrefix(line, "## ") {
			break
		}
		body = append(body, line)
	}
	return strings.TrimSpace(strings.Join(body, "\n"))
}

func verifyOutputs(reviewDir string) []string {
	var missing []string
	for _, l := range lenses {
		name := l.File + ".md"
		info, err := os.Stat(filepath.Join(reviewDir, name))
		if err != nil || info.Size() == 0 {
			missing = append(missing, name)
		}
	}
	return missing
}

func slugify(s string) string {
	re := regexp.MustCompile(`[^a-zA-Z0-9]+`)
	slug := strings.Trim(re.ReplaceAllString(strings.ToLower(s), "-"), "-")
	if slug == "" {
		return "seed"
	}
	if len(slug) > 48 {
		return slug[:48]
	}
	return slug
}

func mustRead(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		fatal("read %s: %v", path, err)
	}
	return string(b)
}

func readOptional(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

func mustWrite(path, content string) {
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		fatal("write %s: %v", path, err)
	}
}

func nonEmpty(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func fatal(format string, args ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}
