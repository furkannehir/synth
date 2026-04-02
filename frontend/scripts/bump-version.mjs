import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const [, , bumpType] = process.argv;
const allowedBumpTypes = new Set(["patch", "minor", "major"]);

if (!allowedBumpTypes.has(bumpType)) {
  console.error("Usage: node scripts/bump-version.mjs <patch|minor|major>");
  process.exit(1);
}

const packageJsonPath = path.resolve("package.json");
const tauriConfPath = path.resolve("src-tauri", "tauri.conf.json");
const cargoTomlPath = path.resolve("src-tauri", "Cargo.toml");

execSync(`npm version ${bumpType} --no-git-tag-version`, { stdio: "inherit" });

const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
const nextVersion = packageJson.version;

const tauriConf = JSON.parse(fs.readFileSync(tauriConfPath, "utf8"));
tauriConf.version = nextVersion;
fs.writeFileSync(tauriConfPath, `${JSON.stringify(tauriConf, null, 2)}\n`);

const cargoToml = fs.readFileSync(cargoTomlPath, "utf8");
const cargoPackageVersionPattern = /(\[package\][\s\S]*?\nversion\s*=\s*")[^"]+(")/;

if (!cargoPackageVersionPattern.test(cargoToml)) {
  console.error("Could not find [package] version in src-tauri/Cargo.toml");
  process.exit(1);
}

const updatedCargoToml = cargoToml.replace(
  cargoPackageVersionPattern,
  `$1${nextVersion}$2`
);

fs.writeFileSync(cargoTomlPath, updatedCargoToml);

console.log(`Synchronized version to ${nextVersion}`);
console.log("Remember to commit and tag manually, for example:");
console.log(`  git commit -am \"chore: release v${nextVersion}\"`);
console.log(`  git tag v${nextVersion}`);
