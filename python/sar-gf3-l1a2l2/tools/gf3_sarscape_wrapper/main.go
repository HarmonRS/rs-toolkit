package main

import (
	"archive/tar"
	"bufio"
	"compress/gzip"
	"embed"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

//go:embed assets/gf3_sarscape_cli.sav
var embedded embed.FS

type config struct {
	configPath    string `json:"-"`
	input         string `json:"input"`
	output        string `json:"output"`
	dem           string `json:"dem"`
	polarizations string `json:"polarizations"`
	idlrt         string `json:"idlrt"`
	keepExtracted bool   `json:"keep_extracted"`
}

type scene struct {
	metaPath    string
	archivePath string
	name        string
}

type sceneFailure struct {
	name  string
	input string
	err   error
}

type batchError struct {
	failures []sceneFailure
}

func (e batchError) Error() string {
	return fmt.Sprintf("batch completed with %d failed scene(s)", len(e.failures))
}

type completedProduct struct {
	polarization string
	path         string
}

func main() {
	cfg := parseFlags()
	if len(os.Args) == 1 {
		var err error
		cfg, err = promptConfig(cfg)
		if err != nil {
			fmt.Printf("ERROR: %v\n", err)
			waitForEnter()
			os.Exit(1)
		}
	}
	if err := run(cfg); err != nil {
		fmt.Printf("ERROR: %v\n", err)
		if len(os.Args) == 1 {
			waitForEnter()
		}
		os.Exit(1)
	}
	if err := saveConfig(cfg.configPath, cfg); err != nil {
		fmt.Printf("WARNING: save config: %v\n", err)
	}
	if len(os.Args) == 1 {
		fmt.Println("Done.")
		waitForEnter()
	}
}

func parseFlags() config {
	cfg := defaultConfig()
	configPath := preScanConfigPath()
	cfg.configPath = configPath
	_ = loadConfig(configPath, &cfg)

	flag.StringVar(&cfg.configPath, "config", configPath, "Config file path")
	flag.StringVar(&cfg.input, "input", cfg.input, "GF-3 input: .meta.xml, .tar.gz, or directory")
	flag.StringVar(&cfg.output, "output", cfg.output, "Output directory")
	flag.StringVar(&cfg.dem, "dem", cfg.dem, "SARscape DEM file")
	flag.StringVar(&cfg.polarizations, "pol", cfg.polarizations, "Polarizations: HH, HV, or HH,HV")
	flag.StringVar(&cfg.idlrt, "idlrt", cfg.idlrt, "Path to idlrt.exe")
	flag.BoolVar(&cfg.keepExtracted, "keep-extracted", cfg.keepExtracted, "Keep extracted archives under output/.gf3_extract")
	flag.Parse()
	return cfg
}

func defaultConfig() config {
	return config{
		dem:           `D:\DEM\COPDEM_GLO30_China_4326_DEM`,
		polarizations: "HH,HV",
		idlrt:         defaultIDLRT(),
		keepExtracted: true,
	}
}

func preScanConfigPath() string {
	defaultPath := defaultConfigPath()
	for i := 1; i < len(os.Args)-1; i++ {
		if os.Args[i] == "-config" {
			return os.Args[i+1]
		}
	}
	return defaultPath
}

func defaultConfigPath() string {
	exe, err := os.Executable()
	if err != nil {
		return "gf3wrapper.json"
	}
	return filepath.Join(filepath.Dir(exe), "gf3wrapper.json")
}

func loadConfig(path string, cfg *config) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var stored struct {
		IDLRTPath     string `json:"idlrt_path"`
		DemFile       string `json:"dem_file"`
		Polarizations string `json:"polarizations"`
		LastInput     string `json:"last_input"`
		LastOutput    string `json:"last_output"`
		IDLRT         string `json:"idlrt"`
		Dem           string `json:"dem"`
		Input         string `json:"input"`
		Output        string `json:"output"`
		KeepExtracted *bool  `json:"keep_extracted"`
	}
	if err := json.Unmarshal(data, &stored); err != nil {
		return err
	}
	if stored.IDLRTPath != "" {
		cfg.idlrt = stored.IDLRTPath
	} else if stored.IDLRT != "" {
		cfg.idlrt = stored.IDLRT
	}
	if stored.DemFile != "" {
		cfg.dem = stored.DemFile
	} else if stored.Dem != "" {
		cfg.dem = stored.Dem
	}
	if stored.Polarizations != "" {
		cfg.polarizations = stored.Polarizations
	}
	if stored.LastInput != "" {
		cfg.input = stored.LastInput
	} else if stored.Input != "" {
		cfg.input = stored.Input
	}
	if stored.LastOutput != "" {
		cfg.output = stored.LastOutput
	} else if stored.Output != "" {
		cfg.output = stored.Output
	}
	if stored.KeepExtracted != nil {
		cfg.keepExtracted = *stored.KeepExtracted
	}
	cfg.configPath = path
	return nil
}

func saveConfig(path string, cfg config) error {
	if path == "" {
		path = defaultConfigPath()
	}
	stored := struct {
		IDLRTPath     string `json:"idlrt_path"`
		DemFile       string `json:"dem_file"`
		Polarizations string `json:"polarizations"`
		LastInput     string `json:"last_input"`
		LastOutput    string `json:"last_output"`
		KeepExtracted bool   `json:"keep_extracted"`
	}{
		IDLRTPath:     cfg.idlrt,
		DemFile:       cfg.dem,
		Polarizations: cfg.polarizations,
		LastInput:     cfg.input,
		LastOutput:    cfg.output,
		KeepExtracted: cfg.keepExtracted,
	}
	data, err := json.MarshalIndent(stored, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

func promptConfig(defaults config) (config, error) {
	reader := bufio.NewReader(os.Stdin)
	cfg := defaults

	fmt.Println("GF-3 SARscape Wrapper")
	fmt.Println()

	cfg.input = prompt(reader, "Input .tar.gz / .meta.xml / folder", cfg.input)
	cfg.output = prompt(reader, "Output folder", cfg.output)
	cfg.dem = prompt(reader, "DEM file", cfg.dem)
	cfg.polarizations = prompt(reader, "Polarizations", cfg.polarizations)
	cfg.idlrt = prompt(reader, "IDL Runtime", cfg.idlrt)

	if cfg.input == "" || cfg.output == "" || cfg.dem == "" {
		return cfg, errors.New("input, output, and DEM are required")
	}
	return cfg, nil
}

func prompt(reader *bufio.Reader, label, defaultValue string) string {
	if defaultValue != "" {
		fmt.Printf("%s [%s]: ", label, defaultValue)
	} else {
		fmt.Printf("%s: ", label)
	}
	text, _ := reader.ReadString('\n')
	text = strings.TrimSpace(text)
	if text == "" {
		return defaultValue
	}
	return text
}

func waitForEnter() {
	fmt.Println()
	fmt.Print("Press Enter to exit...")
	_, _ = bufio.NewReader(os.Stdin).ReadString('\n')
}

func run(cfg config) error {
	if cfg.input == "" || cfg.output == "" || cfg.dem == "" {
		return errors.New("required flags: -input, -output, -dem")
	}
	if _, err := os.Stat(cfg.idlrt); err != nil {
		return fmt.Errorf("idlrt not found: %s: %w", cfg.idlrt, err)
	}
	if _, err := os.Stat(cfg.dem); err != nil {
		return fmt.Errorf("DEM not found: %s: %w", cfg.dem, err)
	}
	if err := os.MkdirAll(cfg.output, 0o755); err != nil {
		return err
	}

	scenes, err := discoverScenes(cfg)
	if err != nil {
		return err
	}
	if len(scenes) == 0 {
		return fmt.Errorf("no *.meta.xml scenes found in %s", cfg.input)
	}

	failures := make([]sceneFailure, 0)
	processed := 0
	skipped := 0
	savPath := ""
	for _, sc := range scenes {
		sceneOut := filepath.Join(cfg.output, sc.name)
		if products, ok := completedSceneOutputs(sceneOut, sc.name, cfg.polarizations); ok {
			recordSceneSkip(sc, sceneOut, products)
			skipped++
			continue
		}
		if err := os.MkdirAll(sceneOut, 0o755); err != nil {
			recordSceneFailure(&failures, sc, err)
			continue
		}
		if sc.archivePath != "" {
			extractDir := filepath.Join(sceneOut, ".gf3_extract")
			fmt.Printf("Extracting %s\n", sc.archivePath)
			if err := extractTarGz(sc.archivePath, extractDir); err != nil {
				recordSceneFailure(&failures, sc, fmt.Errorf("failed to extract archive before processing scene %s: %w", sc.archivePath, err))
				continue
			}
			extractedScenes, err := findMetaXML(extractDir)
			if err != nil {
				recordSceneFailure(&failures, sc, err)
				continue
			}
			if len(extractedScenes) == 0 {
				recordSceneFailure(&failures, sc, fmt.Errorf("no *.meta.xml found in archive: %s", sc.archivePath))
				continue
			}
			sc.metaPath = extractedScenes[0].metaPath
			sc.name = sceneName(sc.metaPath)
		}
		if savPath == "" {
			var err error
			savPath, err = materializeSAV(cfg.output)
			if err != nil {
				recordSceneFailure(&failures, sc, err)
				continue
			}
		}
		if err := runScene(cfg, savPath, sc, sceneOut); err != nil {
			recordSceneFailure(&failures, sc, err)
			continue
		}
		processed++
	}
	printBatchSummary(len(scenes), processed, skipped, failures)
	if len(failures) > 0 {
		return batchError{failures: failures}
	}
	return nil
}

func sceneInput(sc scene) string {
	if sc.archivePath != "" {
		return sc.archivePath
	}
	if sc.metaPath != "" {
		return sc.metaPath
	}
	return sc.name
}

func recordSceneFailure(failures *[]sceneFailure, sc scene, err error) {
	input := sceneInput(sc)

	failure := sceneFailure{name: sc.name, input: input, err: err}
	*failures = append(*failures, failure)

	fmt.Printf("FAILED %s\n", sc.name)
	fmt.Printf("Input %s\n", input)
	fmt.Printf("Reason: %v\n", err)
	fmt.Println("Continuing with next scene.")
}

func recordSceneSkip(sc scene, sceneOut string, products []completedProduct) {
	parts := make([]string, 0, len(products))
	for _, product := range products {
		parts = append(parts, product.polarization+"="+product.path)
	}

	fmt.Printf("SKIPPED %s\n", sc.name)
	fmt.Printf("Input %s\n", sceneInput(sc))
	fmt.Printf("Output already complete %s\n", sceneOut)
	fmt.Printf("Products %s\n", strings.Join(parts, "; "))
}

func printBatchSummary(total, processed, skipped int, failures []sceneFailure) {
	fmt.Println()
	fmt.Printf("Batch summary: %d processed, %d skipped, %d failed, %d total\n", processed, skipped, len(failures), total)
	if len(failures) == 0 {
		return
	}
	fmt.Println("Failed scenes:")
	for _, failure := range failures {
		fmt.Printf("- %s (%s): %v\n", failure.name, failure.input, failure.err)
	}
}

func materializeSAV(outputDir string) (string, error) {
	data, err := embedded.ReadFile("assets/gf3_sarscape_cli.sav")
	if err != nil {
		return "", err
	}
	runtimeDir := filepath.Join(outputDir, ".gf3_runtime")
	if err := os.MkdirAll(runtimeDir, 0o755); err != nil {
		return "", err
	}
	savPath := filepath.Join(runtimeDir, "gf3_sarscape_cli.sav")
	if err := os.WriteFile(savPath, data, 0o644); err != nil {
		return "", err
	}
	return savPath, nil
}

func discoverScenes(cfg config) ([]scene, error) {
	info, err := os.Stat(cfg.input)
	if err != nil {
		return nil, err
	}
	if info.IsDir() {
		return discoverScenesInDir(cfg.input, cfg.output)
	}
	lower := strings.ToLower(cfg.input)
	if strings.HasSuffix(lower, ".meta.xml") {
		return []scene{{metaPath: cfg.input, name: sceneName(cfg.input)}}, nil
	}
	if strings.HasSuffix(lower, ".tar.gz") || strings.HasSuffix(lower, ".tgz") {
		return []scene{{archivePath: cfg.input, name: safeName(trimArchiveExt(filepath.Base(cfg.input)))}}, nil
	}
	return nil, fmt.Errorf("unsupported input type: %s", cfg.input)
}

func discoverScenesInDir(inputDir, outputDir string) ([]scene, error) {
	_ = outputDir
	scenesByName := make(map[string]scene)

	err := filepath.WalkDir(inputDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if d.Name() == ".gf3_extract" {
				return filepath.SkipDir
			}
			return nil
		}
		lower := strings.ToLower(d.Name())
		switch {
		case strings.HasSuffix(lower, ".meta.xml"):
			sc := scene{metaPath: path, name: sceneName(path)}
			key := strings.ToLower(sc.name)
			if _, ok := scenesByName[key]; !ok {
				scenesByName[key] = sc
			}
		case strings.HasSuffix(lower, ".tar.gz") || strings.HasSuffix(lower, ".tgz"):
			sc := scene{archivePath: path, name: safeName(trimArchiveExt(filepath.Base(path)))}
			scenesByName[strings.ToLower(sc.name)] = sc
		}
		return nil
	})
	if err != nil {
		return nil, err
	}

	scenes := make([]scene, 0, len(scenesByName))
	for _, sc := range scenesByName {
		scenes = append(scenes, sc)
	}
	sort.Slice(scenes, func(i, j int) bool {
		return strings.ToLower(scenes[i].name) < strings.ToLower(scenes[j].name)
	})
	return scenes, nil
}

func findMetaXML(root string) ([]scene, error) {
	var scenes []scene
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		if strings.HasSuffix(strings.ToLower(d.Name()), ".meta.xml") {
			scenes = append(scenes, scene{metaPath: path, name: sceneName(path)})
		}
		return nil
	})
	return scenes, err
}

func uniqueScenes(scenes []scene) []scene {
	seen := make(map[string]bool, len(scenes))
	out := make([]scene, 0, len(scenes))
	for _, sc := range scenes {
		key := filepath.Clean(sc.metaPath)
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, sc)
	}
	return out
}

func runScene(cfg config, savPath string, sc scene, sceneOut string) error {
	fmt.Printf("Processing %s\n", sc.metaPath)
	fmt.Printf("Output %s\n", sceneOut)

	cmd := exec.Command(cfg.idlrt, savPath, "-args", sc.metaPath, sceneOut, cfg.dem, cfg.polarizations)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Dir = sceneOut

	if err := cmd.Start(); err != nil {
		return err
	}

	done := make(chan error, 1)
	go func() {
		done <- cmd.Wait()
	}()

	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case err := <-done:
			fmt.Printf("\r%-100s\r", "")
			if err != nil {
				return fmt.Errorf("scene failed %s: %w", sc.metaPath, err)
			}
			fmt.Println("Completed", sc.name)
			return nil
		case <-ticker.C:
			fmt.Printf("\r%s", progressLine(sceneOut, sc.name, cfg.polarizations))
		}
	}
}

func progressLine(sceneOut, sceneNameValue, polarizations string) string {
	stage, done, total := progressStage(sceneOut, sceneNameValue, polarizations)
	width := 28
	filled := 0
	if total > 0 {
		filled = done * width / total
	}
	if filled > width {
		filled = width
	}
	bar := strings.Repeat("#", filled) + strings.Repeat("-", width-filled)
	return fmt.Sprintf("[%s] %2d/%2d %s", bar, done, total, stage)
}

func progressStage(sceneOut, sceneNameValue, polarizations string) (string, int, int) {
	pols := requestedPolarizations(polarizations)
	checks := make([]struct {
		label string
		path  string
	}, 0, len(pols)*4)

	for _, pol := range pols {
		checks = append(checks, struct {
			label string
			path  string
		}{"import " + pol, filepath.Join(sceneOut, "*_"+pol+"_slc.sml")})
	}

	for _, pol := range pols {
		lower := strings.ToLower(pol)
		prefix := sceneNameValue + "_" + lower
		checks = append(checks,
			struct {
				label string
				path  string
			}{"multilook " + pol, filepath.Join(sceneOut, prefix+"_ml.sml")},
			struct {
				label string
				path  string
			}{"filter " + pol, filepath.Join(sceneOut, prefix+"_filt.sml")},
			struct {
				label string
				path  string
			}{"geocode " + pol, filepath.Join(sceneOut, prefix+"_geo.sml")},
		)
	}

	done := 0
	for _, check := range checks {
		if matched(check.path) {
			done++
			continue
		}
		return check.label, done, len(checks)
	}
	return "finishing", done, len(checks)
}

func completedSceneOutputs(sceneOut, sceneNameValue, polarizations string) ([]completedProduct, bool) {
	info, err := os.Stat(sceneOut)
	if err != nil || !info.IsDir() {
		return nil, false
	}

	pols := requestedPolarizations(polarizations)
	products := make([]completedProduct, 0, len(pols))
	for _, pol := range pols {
		path, ok := completedGeoProduct(sceneOut, sceneNameValue, pol)
		if !ok {
			return nil, false
		}
		products = append(products, completedProduct{polarization: pol, path: path})
	}
	return products, true
}

func completedGeoProduct(sceneOut, sceneNameValue, polarization string) (string, bool) {
	lower := strings.ToLower(polarization)
	exact := filepath.Join(sceneOut, sceneNameValue+"_"+lower+"_geo.sml")
	if completeGeoSML(exact) {
		return exact, true
	}

	matches, err := filepath.Glob(filepath.Join(sceneOut, "*_"+lower+"_geo.sml"))
	if err != nil {
		return "", false
	}
	sort.Strings(matches)
	for _, match := range matches {
		if completeGeoSML(match) {
			return match, true
		}
	}
	return "", false
}

func completeGeoSML(path string) bool {
	info, err := os.Stat(path)
	if err != nil || info.IsDir() || info.Size() == 0 {
		return false
	}

	dataPath := strings.TrimSuffix(path, ".sml")
	dataInfo, err := os.Stat(dataPath)
	return err == nil && !dataInfo.IsDir() && dataInfo.Size() > 0
}

func requestedPolarizations(value string) []string {
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		pol := strings.ToUpper(strings.TrimSpace(part))
		if pol == "" {
			continue
		}
		if pol == "ALL" {
			return []string{"HH", "HV"}
		}
		out = append(out, pol)
	}
	if len(out) == 0 {
		return []string{"HH", "HV"}
	}
	return out
}

func matched(pattern string) bool {
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return false
	}
	return len(matches) > 0
}

func extractTarGz(src, dst string) error {
	dst = filepath.Clean(dst)
	tmpDst := dst + ".tmp"

	if err := os.RemoveAll(tmpDst); err != nil {
		return fmt.Errorf("remove stale temporary extraction directory %s: %w", tmpDst, err)
	}
	if err := os.MkdirAll(tmpDst, 0o755); err != nil {
		return err
	}
	if err := extractTarGzToDir(src, tmpDst); err != nil {
		_ = os.RemoveAll(tmpDst)
		return err
	}
	if err := os.RemoveAll(dst); err != nil {
		_ = os.RemoveAll(tmpDst)
		return fmt.Errorf("replace extraction directory %s: %w", dst, err)
	}
	if err := os.Rename(tmpDst, dst); err != nil {
		_ = os.RemoveAll(tmpDst)
		return fmt.Errorf("move completed extraction into %s: %w", dst, err)
	}
	return nil
}

func extractTarGzToDir(src, dst string) error {
	f, err := os.Open(src)
	if err != nil {
		return err
	}
	defer f.Close()

	gz, err := gzip.NewReader(f)
	if err != nil {
		return archiveReadError(src, "", err)
	}
	defer gz.Close()

	tr := tar.NewReader(gz)
	var currentEntry string
	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return archiveReadError(src, currentEntry, err)
		}
		currentEntry = hdr.Name
		target := filepath.Join(dst, filepath.Clean(hdr.Name))
		if !strings.HasPrefix(target, filepath.Clean(dst)+string(os.PathSeparator)) && filepath.Clean(target) != filepath.Clean(dst) {
			return fmt.Errorf("archive entry escapes destination: %s", hdr.Name)
		}
		switch hdr.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(target, 0o755); err != nil {
				return err
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return err
			}
			out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
			if err != nil {
				return err
			}
			_, copyErr := io.Copy(out, tr)
			closeErr := out.Close()
			if copyErr != nil {
				return archiveReadError(src, hdr.Name, copyErr)
			}
			if closeErr != nil {
				return closeErr
			}
		}
	}
	return nil
}

func archiveReadError(src, entry string, err error) error {
	detail := src
	if info, statErr := os.Stat(src); statErr == nil {
		detail = fmt.Sprintf("%s (%d bytes)", src, info.Size())
	}
	if entry != "" {
		detail = fmt.Sprintf("%s while reading %s", detail, entry)
	}
	if errors.Is(err, io.ErrUnexpectedEOF) || strings.Contains(strings.ToLower(err.Error()), "unexpected eof") {
		return fmt.Errorf("archive appears truncated or incomplete: %s: %w; re-copy or re-download the .tar.gz", detail, err)
	}
	return fmt.Errorf("read archive %s: %w", detail, err)
}

func sceneName(metaPath string) string {
	base := filepath.Base(metaPath)
	base = strings.TrimSuffix(base, ".meta.xml")
	base = strings.TrimSuffix(base, ".META.XML")
	return safeName(base)
}

func safeName(s string) string {
	replacer := strings.NewReplacer(" ", "_", ":", "_", "/", "_", "\\", "_")
	return replacer.Replace(s)
}

func trimArchiveExt(name string) string {
	lower := strings.ToLower(name)
	switch {
	case strings.HasSuffix(lower, ".tar.gz"):
		return name[:len(name)-7]
	case strings.HasSuffix(lower, ".tgz"):
		return name[:len(name)-4]
	default:
		return strings.TrimSuffix(name, filepath.Ext(name))
	}
}

func defaultIDLRT() string {
	if v := os.Getenv("IDLRT_PATH"); v != "" {
		return v
	}
	return `C:\Program Files\Harris\ENVI56\IDL88\bin\bin.x86_64\idlrt.exe`
}
