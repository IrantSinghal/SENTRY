const { execSync } = require('child_process');
const path = require('path');

console.log("Seeding vendors and database baseline via seed.py...");
try {
  const projectRoot = path.resolve(__dirname, '..');
  execSync('python backend/db/seed.py', { cwd: projectRoot, stdio: 'inherit' });
  console.log("Vendor seeding completed successfully.");
} catch (err) {
  console.error("Failed to seed vendors via Python seed script:", err.message);
  process.exit(1);
}
