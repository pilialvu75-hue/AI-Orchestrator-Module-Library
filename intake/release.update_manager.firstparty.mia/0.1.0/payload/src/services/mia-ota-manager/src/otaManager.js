import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { MAX_BACKUP_HISTORY } from '../../shared/constants.js';
import { compareVersions } from '../../shared/version.js';

export class ModuleLoader {
  constructor() {
    this.modules = new Map();
  }

  loadModule(moduleSpec) {
    const deps = moduleSpec.dependencies ?? [];
    const missing = deps.filter((dep) => !this.modules.has(dep));
    if (missing.length) {
      throw new Error(`Missing dependencies: ${missing.join(', ')}`);
    }

    this.modules.set(moduleSpec.name, {
      name: moduleSpec.name,
      version: moduleSpec.version,
      dependencies: deps,
      content: moduleSpec.content ?? '',
      updatedAt: new Date().toISOString(),
    });

    return this.modules.get(moduleSpec.name);
  }

  unloadModule(moduleName) {
    this.modules.delete(moduleName);
  }

  hotReload(moduleSpec) {
    this.unloadModule(moduleSpec.name);
    return this.loadModule(moduleSpec);
  }

  manageDependencies(moduleSpec) {
    return (moduleSpec.dependencies ?? []).every((dep) => this.modules.has(dep));
  }
}

export class BackupManager {
  constructor() {
    this.history = [];
  }

  compressModules(modules) {
    return zlib.gzipSync(Buffer.from(JSON.stringify(modules), 'utf8'));
  }

  createBackup({ version, modules }) {
    const archive = this.compressModules(modules);
    const sha256 = crypto.createHash('sha256').update(archive).digest('hex');
    const backup = {
      version,
      sha256,
      createdAt: new Date().toISOString(),
      archive,
    };
    this.history.unshift(backup);
    this.history = this.history.slice(0, MAX_BACKUP_HISTORY);
    return backup;
  }

  uploadToGithub({ version, sha256 }) {
    return {
      tag: version,
      releaseName: `MIA OTA ${version}`,
      checksum: sha256,
      uploaded: true,
    };
  }

  versioning() {
    return this.history.map(({ version, sha256, createdAt }) => ({ version, sha256, createdAt }));
  }
}

export class RollbackManager {
  constructor({ crashThreshold = 3 } = {}) {
    this.crashThreshold = crashThreshold;
    this.crashCount = 0;
    this.incidents = [];
  }

  detectCrash(error) {
    this.crashCount += 1;
    this.incidents.push({
      message: error?.message ?? String(error ?? 'unknown'),
      at: new Date().toISOString(),
      crashCount: this.crashCount,
    });
    return this.crashCount >= this.crashThreshold;
  }

  rollbackToPrevious(stableVersions) {
    if (!stableVersions.length) {
      throw new Error('No stable version available for rollback');
    }
    return stableVersions[stableVersions.length - 1];
  }

  compareVersions(currentVersion, previousVersion) {
    return compareVersions(currentVersion, previousVersion);
  }

  restoreBackup(backup) {
    this.crashCount = 0;
    return {
      restoredVersion: backup.version,
      restoredAt: new Date().toISOString(),
    };
  }
}

export class HealthMonitor {
  constructor() {
    this.logs = [];
  }

  monitorCrashes(err) {
    this.logs.push({ type: 'crash', message: err.message, at: new Date().toISOString() });
  }

  trackPerformance(metric) {
    this.logs.push({ type: 'performance', ...metric, at: new Date().toISOString() });
  }

  logErrors(err) {
    this.logs.push({ type: 'error', message: err.message, at: new Date().toISOString() });
  }

  triggerRollback(rollbackManager, err) {
    this.monitorCrashes(err);
    return rollbackManager.detectCrash(err);
  }
}

export class AutoUpdateEngine {
  checkUpdates(currentVersion, availableVersions) {
    const sorted = [...availableVersions].sort((a, b) => compareVersions(a.version, b.version));
    const latest = sorted.at(-1);
    if (!latest || compareVersions(latest.version, currentVersion) <= 0) {
      return null;
    }
    return latest;
  }

  async downloadModules(update, downloader) {
    return downloader(update);
  }

  verifyIntegrity(buffer, expectedSha256) {
    const actual = crypto.createHash('sha256').update(buffer).digest('hex');
    return actual === expectedSha256;
  }

  applyUpdate(moduleLoader, updateBundle) {
    updateBundle.modules.forEach((moduleSpec) => moduleLoader.hotReload(moduleSpec));
    return { appliedVersion: updateBundle.version, appliedAt: new Date().toISOString() };
  }
}

export class OTAManager {
  constructor({
    autoUpdateEngine = new AutoUpdateEngine(),
    backupManager = new BackupManager(),
    rollbackManager = new RollbackManager(),
    moduleLoader = new ModuleLoader(),
    healthMonitor = new HealthMonitor(),
  } = {}) {
    this.autoUpdateEngine = autoUpdateEngine;
    this.backupManager = backupManager;
    this.rollbackManager = rollbackManager;
    this.moduleLoader = moduleLoader;
    this.healthMonitor = healthMonitor;
    this.stableVersions = [];
  }

  async runUpdateCycle({
    currentVersion,
    availableUpdates,
    downloader,
    monitor,
  }) {
    const candidate = this.autoUpdateEngine.checkUpdates(currentVersion, availableUpdates);
    if (!candidate) {
      return { status: 'no-update', currentVersion };
    }

    const bundle = await this.autoUpdateEngine.downloadModules(candidate, downloader);
    if (!this.autoUpdateEngine.verifyIntegrity(bundle.payload, bundle.sha256)) {
      return { status: 'integrity-failed', version: bundle.version };
    }

    const modulesWithMissingDeps = bundle.modules.filter((m) => !this.moduleLoader.manageDependencies(m));
    if (modulesWithMissingDeps.length) {
      return { status: 'dependency-failed', modules: modulesWithMissingDeps.map((m) => m.name) };
    }

    const applied = this.autoUpdateEngine.applyUpdate(this.moduleLoader, bundle);

    try {
      await monitor(bundle.version);
      this.stableVersions.push(bundle.version);
      const backup = this.backupManager.createBackup({ version: bundle.version, modules: bundle.modules });
      const release = this.backupManager.uploadToGithub({ version: bundle.version, sha256: backup.sha256 });
      return {
        status: 'stable',
        applied,
        backup: { version: backup.version, sha256: backup.sha256 },
        release,
      };
    } catch (err) {
      const shouldRollback = this.healthMonitor.triggerRollback(this.rollbackManager, err);
      if (shouldRollback && this.stableVersions.length) {
        const rollbackVersion = this.rollbackManager.rollbackToPrevious(this.stableVersions);
        return {
          status: 'rolled-back',
          rollbackVersion,
          reason: err.message,
        };
      }
      return { status: 'monitoring-failed', reason: err.message };
    }
  }
}
