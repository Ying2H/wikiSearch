import { promises as fs } from "node:fs";
import path from "node:path";
import process from "node:process";
import * as pagefind from "pagefind";

function parseArgs(argv) {
  const args = {
    records: "data/cache",
    output: "data/publish/pagefind",
  };
  for (let i = 0; i < argv.length; i += 1) {
    const value = argv[i];
    if (value === "--records") args.records = argv[++i];
    else if (value === "--output") args.output = argv[++i];
    else if (value === "--help" || value === "-h") {
      console.log("Usage: npm run build:index -- [--records DIR] [--output DIR]");
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${value}`);
    }
  }
  return args;
}

async function findRecordFiles(root) {
  const result = [];
  async function visit(directory) {
    const entries = await fs.readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(directory, entry.name);
      if (entry.isDirectory()) await visit(fullPath);
      else if (entry.isFile() && entry.name === "record.json") result.push(fullPath);
    }
  }
  await visit(root);
  return result.sort();
}

function validateRecord(record, sourcePath) {
  if (!record || typeof record !== "object") throw new Error(`${sourcePath}: record must be an object`);
  for (const key of ["url", "content", "language"]) {
    if (typeof record[key] !== "string" || record[key].length === 0) {
      throw new Error(`${sourcePath}: ${key} must be a non-empty string`);
    }
  }
  if (!/^https?:\/\//i.test(record.url)) throw new Error(`${sourcePath}: URL must be http(s)`);
  if (record.meta && Object.values(record.meta).some((value) => typeof value !== "string")) {
    throw new Error(`${sourcePath}: meta values must be strings`);
  }
  if (record.filters && Object.values(record.filters).some((value) => !Array.isArray(value) || value.some((item) => typeof item !== "string"))) {
    throw new Error(`${sourcePath}: filter values must be string arrays`);
  }
  if (record.sort && Object.values(record.sort).some((value) => typeof value !== "string")) {
    throw new Error(`${sourcePath}: sort values must be strings`);
  }
}

async function pathExists(target) {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

async function publishDirectory(staged, output) {
  await fs.mkdir(path.dirname(output), { recursive: true });
  const backup = `${output}.previous-${process.pid}-${Date.now()}`;
  let movedPrevious = false;
  try {
    if (await pathExists(output)) {
      await fs.rename(output, backup);
      movedPrevious = true;
    }
    await fs.rename(staged, output);
    if (movedPrevious) await fs.rm(backup, { recursive: true, force: true });
  } catch (error) {
    if (movedPrevious && !(await pathExists(output)) && (await pathExists(backup))) {
      await fs.rename(backup, output);
    }
    throw error;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const recordsRoot = path.resolve(args.records);
  const output = path.resolve(args.output);
  const staged = `${output}.staged-${process.pid}-${Date.now()}`;
  const files = await findRecordFiles(recordsRoot);
  if (files.length === 0) throw new Error(`No record.json files found below ${recordsRoot}`);

  const { index } = await pagefind.createIndex({
    writePlayground: false,
    verbose: false,
  });
  try {
    let added = 0;
    for (const file of files) {
      const record = JSON.parse(await fs.readFile(file, "utf8"));
      validateRecord(record, file);
      const result = await index.addCustomRecord(record);
      if (result.errors?.length) throw new Error(`${file}: ${result.errors.join("; ")}`);
      added += 1;
    }
    const written = await index.writeFiles({ outputPath: staged });
    if (written.errors?.length) throw new Error(written.errors.join("; "));
    await pagefind.close();
    await publishDirectory(staged, output);
    console.log(JSON.stringify({ records: added, output }, null, 2));
  } catch (error) {
    await pagefind.close();
    await fs.rm(staged, { recursive: true, force: true });
    throw error;
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
