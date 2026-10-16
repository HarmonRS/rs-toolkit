package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCompletedSceneOutputsRequiresGeoSMLAndDataForAllPolarizations(t *testing.T) {
	dir := t.TempDir()
	sceneName := "GF3_TEST_SCENE"

	writeFile(t, filepath.Join(dir, sceneName+"_hh_geo.sml"), "hh sml")
	writeFile(t, filepath.Join(dir, sceneName+"_hh_geo"), "hh data")
	writeFile(t, filepath.Join(dir, sceneName+"_hv_geo.sml"), "hv sml")
	writeFile(t, filepath.Join(dir, sceneName+"_hv_geo"), "hv data")

	products, ok := completedSceneOutputs(dir, sceneName, "HH,HV")
	if !ok {
		t.Fatal("expected completed scene outputs")
	}
	if len(products) != 2 {
		t.Fatalf("expected 2 completed products, got %d", len(products))
	}
}

func TestCompletedSceneOutputsRejectsMissingDataFile(t *testing.T) {
	dir := t.TempDir()
	sceneName := "GF3_TEST_SCENE"

	writeFile(t, filepath.Join(dir, sceneName+"_hh_geo.sml"), "hh sml")
	writeFile(t, filepath.Join(dir, sceneName+"_hv_geo.sml"), "hv sml")
	writeFile(t, filepath.Join(dir, sceneName+"_hv_geo"), "hv data")

	if _, ok := completedSceneOutputs(dir, sceneName, "HH,HV"); ok {
		t.Fatal("expected incomplete scene when one geocoded data file is missing")
	}
}

func TestCompletedSceneOutputsRequiresRequestedPolarizations(t *testing.T) {
	dir := t.TempDir()
	sceneName := "GF3_TEST_SCENE"

	writeFile(t, filepath.Join(dir, sceneName+"_hh_geo.sml"), "hh sml")
	writeFile(t, filepath.Join(dir, sceneName+"_hh_geo"), "hh data")

	if _, ok := completedSceneOutputs(dir, sceneName, "HH,HV"); ok {
		t.Fatal("expected incomplete scene when HV output is missing")
	}

	if _, ok := completedSceneOutputs(dir, sceneName, "HH"); !ok {
		t.Fatal("expected completed scene for HH-only request")
	}
}

func writeFile(t *testing.T, path, value string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(value), 0o644); err != nil {
		t.Fatal(err)
	}
}
