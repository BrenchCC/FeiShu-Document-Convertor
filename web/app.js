class FeishuImportApp {
    constructor() {
        this.apiBase = '/api';
        this.localSelectionTarget = '';
        this.initElements();
        this.bindEvents();
        this.loadConfig();
        this.updateFolderRootSubdirState();
    }

    initElements() {
        this.$localBtn = document.querySelector('[data-source="local"]');
        this.$githubBtn = document.querySelector('[data-source="github"]');
        this.$localConfig = document.getElementById('localConfig');
        this.$githubConfig = document.getElementById('githubConfig');
        this.$runBtn = document.getElementById('runBtn');
        this.$configBtn = document.getElementById('configBtn');
        this.$toggleAdvanced = document.getElementById('toggleAdvanced');
        this.$advancedOptions = document.getElementById('advancedOptions');
        this.$configModal = document.getElementById('configModal');
        this.$saveConfig = document.getElementById('saveConfig');
        this.$cancelConfig = document.getElementById('cancelConfig');
        this.$closeConfigModal = document.getElementById('closeConfigModal');
        this.$logContainer = document.getElementById('logContainer');
        this.$clearLog = document.getElementById('clearLog');
        this.$browseBtn = document.getElementById('browseBtn');
        this.$importType = document.getElementById('importType');
        this.$directoryInput = document.getElementById('directoryInput');
        this.$fileInput = document.getElementById('fileInput');
        this.$folderRootSubdir = document.getElementById('folderRootSubdir');
        this.$folderRootSubdirName = document.getElementById('folderRootSubdirName');
        if (this.$importType) {
            const importTypeGroup = this.$importType.closest('.form-group');
            if (importTypeGroup) {
                importTypeGroup.style.display = 'none';
            }
        }
    }

    bindEvents() {
        this.$localBtn.addEventListener('click', () => this.switchSource('local'));
        this.$githubBtn.addEventListener('click', () => this.switchSource('github'));
        this.$runBtn.addEventListener('click', () => this.runImport());
        this.$configBtn.addEventListener('click', () => this.showConfig());
        this.$toggleAdvanced.addEventListener('click', () => this.toggleAdvanced());
        this.$saveConfig.addEventListener('click', () => this.saveConfig());
        this.$cancelConfig.addEventListener('click', () => this.hideConfig());
        this.$closeConfigModal.addEventListener('click', () => this.hideConfig());
        this.$configModal.addEventListener('click', (e) => {
            if (e.target === this.$configModal) {
                this.hideConfig();
            }
        });
        this.$clearLog.addEventListener('click', () => this.clearLog());
        this.$browseBtn.addEventListener('click', () => this.browseLocalPath());
        this.$directoryInput.addEventListener('change', (event) => this.handleLocalSelection(event, 'directory'));
        this.$fileInput.addEventListener('change', (event) => this.handleLocalSelection(event, 'file'));
        if (this.$folderRootSubdir) {
            this.$folderRootSubdir.addEventListener('change', () => this.updateFolderRootSubdirState());
        }
    }

    switchSource(source) {
        const localActive = source === 'local';
        const githubActive = source === 'github';

        this.$localBtn.classList.toggle('active', localActive);
        this.$githubBtn.classList.toggle('active', githubActive);
        this.$localConfig.classList.toggle('hidden', !localActive);
        this.$githubConfig.classList.toggle('hidden', !githubActive);

        this.addLog(`已切换到 ${localActive ? '本地目录' : 'GitHub 仓库'} 源配置`, 'info');
    }

    toggleAdvanced() {
        const isHidden = this.$advancedOptions.classList.contains('hidden');
        this.$advancedOptions.classList.toggle('hidden', !isHidden);
        const icon = this.$toggleAdvanced.querySelector('i');
        const text = isHidden ? '收起' : '展开';
        icon.className = isHidden ? 'fas fa-chevron-up' : 'fas fa-chevron-down';
        this.$toggleAdvanced.querySelector('span').textContent = text;
    }

    showConfig() {
        this.$configModal.classList.remove('hidden');
        this.$configModal.style.display = 'flex';
    }

    hideConfig() {
        this.$configModal.classList.add('hidden');
        this.$configModal.style.display = 'none';
    }

    loadConfig() {
        const config = localStorage.getItem('feishuImportConfig');
        if (!config) {
            return;
        }

        const parsed = JSON.parse(config);
        Object.keys(parsed).forEach((key) => {
            const element = document.getElementById(key);
            if (!element) {
                return;
            }
            if (element.type === 'checkbox') {
                element.checked = parsed[key];
            } else {
                element.value = parsed[key];
            }
        });
        this.addLog('配置已加载', 'info');
    }

    saveConfig() {
        const config = {
            feishuAppId: this.getElementValue('feishuAppId'),
            feishuAppSecret: this.getElementValue('feishuAppSecret'),
            feishuFolderToken: this.getElementValue('feishuFolderToken'),
            feishuWebhookUrl: this.getElementValue('feishuWebhookUrl')
        };

        localStorage.setItem('feishuImportConfig', JSON.stringify(config));
        this.updateBackendConfig(config);

        this.hideConfig();
        this.showToast('配置已保存', 'success');
        this.addLog('应用配置已保存', 'success');
    }

    async updateBackendConfig(config) {
        try {
            const response = await fetch(`${this.apiBase}/system/config`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('更新配置失败:', error);
            this.addLog(`配置更新失败: ${error.message}`, 'error');
        }
    }

    async runImport() {
        if (!this.validateForm()) {
            return;
        }

        this.$runBtn.disabled = true;
        this.$runBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 导入中...';
        this.clearLog();
        this.updateStatus(0, 0, 0, 0);

        this.addLog('任务开始', 'info');
        await this.startImportProcess();
    }

    validateForm() {
        const source = this.getSourceType();

        if (source === 'local') {
            const localPath = this.getElementValue('localPath').trim();
            if (!localPath) {
                const targetName = this.getImportType() === 'file' ? 'Markdown 文件' : '本地目录';
                this.showToast(`请选择${targetName}路径`, 'error');
                return false;
            }
        } else {
            const githubRepo = this.getElementValue('githubRepo').trim();
            if (!githubRepo) {
                this.showToast('请输入 GitHub 仓库地址', 'error');
                return false;
            }
        }

        return true;
    }

    async startImportProcess() {
        try {
            const request = this.buildImportRequest();
            const response = await fetch(`${this.apiBase}/import/start`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(request)
            });

            if (!response.ok) {
                throw new Error(`启动任务失败: ${response.statusText}`);
            }

            const result = await response.json();
            const taskId = result.task_id;
            this.addLog(`任务已启动，任务ID: ${taskId}`, 'success');
            await this.monitorTask(taskId);
        } catch (error) {
            console.error('导入失败:', error);
            this.addLog(`导入失败: ${error.message}`, 'error');
            this.showToast(`导入失败: ${error.message}`, 'error');

            this.$runBtn.disabled = false;
            this.$runBtn.innerHTML = '<i class="fas fa-play"></i> 开始导入';
        }
    }

    buildImportRequest() {
        const source = this.getSourceType();
        const githubRef = this.getElementValue('githubRef').trim();
        const maxWorkers = Number.parseInt(this.getElementValue('maxWorkers'), 10) || 1;
        const chunkWorkers = Number.parseInt(this.getElementValue('chunkWorkers'), 10) || 2;
        const tocFile = this.getElementValue('tocFile').trim() || 'TABLE_OF_CONTENTS.md';
        const folderNavTitle = this.getElementValue('folderNavTitle').trim() || '00-导航总目录';
        const folderRootSubdir = this.getCheckboxValue('folderRootSubdir');
        const folderRootSubdirName = folderRootSubdir ? this.getElementValue('folderRootSubdirName').trim() : '';
        const llmMaxCalls = Number.parseInt(this.getElementValue('llmMaxCalls'), 10);

        return {
            source_type: source,
            import_type: source === 'local' ? this.getImportType() : undefined,
            path: source === 'local'
                ? this.getElementValue('localPath').trim()
                : this.getElementValue('githubRepo').trim(),
            write_mode: this.getElementValue('writeMode'),
            space_name: this.getOptionalValue('spaceName'),
            space_id: this.getOptionalValue('spaceId'),
            chat_id: this.getOptionalValue('chatId'),
            ref: source === 'github' ? githubRef || undefined : undefined,
            branch: source === 'github' ? githubRef || undefined : undefined,
            commit: undefined,
            subdir: source === 'github' ? this.getOptionalValue('githubSubdir') : undefined,
            structure_order: this.getElementValue('structureOrder') || 'toc_first',
            toc_file: tocFile,
            folder_subdirs: this.getCheckboxValue('folderSubdirs'),
            folder_root_subdir: folderRootSubdir,
            folder_root_subdir_name: folderRootSubdirName,
            folder_nav_doc: this.getCheckboxValue('folderNavDoc'),
            folder_nav_title: folderNavTitle,
            llm_fallback: this.getElementValue('llmFallback') || 'toc_ambiguity',
            llm_max_calls: Number.isNaN(llmMaxCalls) ? 3 : Math.max(0, llmMaxCalls),
            skip_root_readme: this.getCheckboxValue('skipRootReadme'),
            max_workers: maxWorkers,
            chunk_workers: chunkWorkers,
            notify_level: this.getElementValue('notifyLevel') || 'normal',
            dry_run: this.getCheckboxValue('dryRun')
        };
    }

    updateFolderRootSubdirState() {
        if (!this.$folderRootSubdir || !this.$folderRootSubdirName) {
            return;
        }
        const enabled = Boolean(this.$folderRootSubdir.checked);
        this.$folderRootSubdirName.disabled = !enabled;
        if (!enabled) {
            this.$folderRootSubdirName.value = '';
        }
    }

    async monitorTask(taskId) {
        const pollInterval = 2000;
        let isCompleted = false;

        while (!isCompleted) {
            try {
                const response = await fetch(`${this.apiBase}/import/status/${taskId}`);

                if (!response.ok) {
                    throw new Error(`获取任务状态失败: ${response.statusText}`);
                }

                const status = await response.json();

                if (status.progress > 0) {
                    this.updateProgress(status.progress);
                }

                if (status.message) {
                    this.addLog(status.message, 'info');
                }

                if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
                    isCompleted = true;
                    await this.getTaskResult(taskId, status.status);
                } else {
                    await this.delay(pollInterval);
                }
            } catch (error) {
                console.error('监控任务失败:', error);
                this.addLog(`任务监控失败: ${error.message}`, 'error');
                await this.delay(pollInterval);
            }
        }
    }

    async getTaskResult(taskId, status) {
        try {
            const response = await fetch(`${this.apiBase}/import/result/${taskId}`);

            if (!response.ok) {
                throw new Error(`获取任务结果失败: ${response.statusText}`);
            }

            const result = await response.json();
            this.updateStatus(result.total, result.success, result.failed, result.skipped);

            if (result.failures.length > 0) {
                this.addLog(`失败文件: ${result.failures.join(', ')}`, 'error');
            }

            if (result.skipped_items.length > 0) {
                this.addLog(`跳过文件: ${result.skipped_items.join(', ')}`, 'warning');
            }

            const message = status === 'completed'
                ? `任务完成！成功导入 ${result.success} 个文档，失败 ${result.failed} 个，跳过 ${result.skipped} 个`
                : status === 'failed'
                    ? `任务失败！共处理 ${result.total} 个文档，成功 ${result.success} 个，失败 ${result.failed} 个，跳过 ${result.skipped} 个`
                    : '任务已取消';

            const toastType = status === 'completed' ? 'success' : status === 'failed' ? 'error' : 'warning';
            this.showToast(message, toastType);
            this.addLog(message, toastType);
        } catch (error) {
            console.error('获取任务结果失败:', error);
            this.addLog(`获取任务结果失败: ${error.message}`, 'error');
        }

        this.$runBtn.disabled = false;
        this.$runBtn.innerHTML = '<i class="fas fa-play"></i> 开始导入';
    }

    updateProgress(percent) {
        this.addLog(`进度: ${percent}%`, 'info');
    }

    updateStatus(total, success, failed, skipped) {
        document.getElementById('totalCount').textContent = total;
        document.getElementById('successCount').textContent = success;
        document.getElementById('failedCount').textContent = failed;
        document.getElementById('skippedCount').textContent = skipped;
    }

    addLog(message, type = 'info') {
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;

        const icon = this.getIconForType(type);
        const time = new Date().toLocaleTimeString('zh-CN');

        entry.innerHTML = `
            <i class="${icon}"></i>
            <span>[${time}] ${message}</span>
        `;

        this.$logContainer.appendChild(entry);
        this.$logContainer.scrollTop = this.$logContainer.scrollHeight;
    }

    getIconForType(type) {
        const icons = {
            info: 'fas fa-info-circle',
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle'
        };
        return icons[type] || icons.info;
    }

    clearLog() {
        this.$logContainer.innerHTML = `
            <div class="log-entry info">
                <i class="fas fa-info-circle"></i>
                <span>等待开始任务...</span>
            </div>
        `;
    }

    async browseLocalPath() {
        const target = this.inferSelectionTarget();
        if (target === 'auto') {
            const fileSelected = await this.triggerPickerAndWait(this.$fileInput);
            if (!fileSelected) {
                this.$directoryInput.click();
            }
            return;
        }
        if (target === 'file') {
            this.$fileInput.click();
            return;
        }
        this.$directoryInput.click();
    }

    async handleLocalSelection(event, target) {
        const files = Array.from(event.target.files || []);
        if (files.length === 0) {
            return;
        }
        try {
            const payload = await this.uploadLocalSelection(files, target);
            const selectedPath = payload.path || '';
            document.getElementById('localPath').value = selectedPath;
            this.localSelectionTarget = target;
            const label = target === 'file' ? '文件' : '目录';
            this.addLog(`已选择${label}并上传：${selectedPath}`, 'info');
        } catch (error) {
            this.showToast(`路径选择失败: ${error.message}`, 'error');
            this.addLog(`路径选择失败: ${error.message}`, 'error');
        } finally {
            event.target.value = '';
        }
    }

    async uploadLocalSelection(files, target) {
        const formData = new FormData();
        formData.append('target', target);
        const entries = files.map((file) => {
            const relativePath = target === 'directory'
                ? (file.webkitRelativePath || file.name)
                : file.name;
            return {
                relative_path: relativePath
            };
        });
        formData.append('entries_json', JSON.stringify(entries));
        files.forEach((file) => {
            formData.append('files', file, file.name);
        });

        const response = await fetch(`${this.apiBase}/sources/local/upload`, {
            method: 'POST',
            body: formData
        });
        const payload = await response.json();
        if (!response.ok) {
            const detail = payload.detail || '上传失败';
            throw new Error(detail);
        }
        return payload;
    }

    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.classList.remove('hidden', 'show', 'success', 'error', 'warning');

        const toastIcon = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };

        const messageEl = document.querySelector('.toast-message');
        const iconEl = document.querySelector('.toast-icon');

        iconEl.className = toastIcon[type];
        messageEl.textContent = message;
        toast.classList.add(type);

        setTimeout(() => {
            toast.classList.add('show');
        }, 100);

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.classList.add('hidden');
            }, 300);
        }, 3000);
    }

    getSourceType() {
        return this.$localBtn.classList.contains('active') ? 'local' : 'github';
    }

    getImportType() {
        return this.inferSelectionTarget();
    }

    inferSelectionTarget() {
        const localPath = this.getElementValue('localPath').trim().toLowerCase();
        if (localPath.endsWith('.md') || localPath.endsWith('.markdown')) {
            return 'file';
        }
        if (localPath) {
            return 'directory';
        }
        if (this.localSelectionTarget) {
            return this.localSelectionTarget;
        }
        return 'auto';
    }

    triggerPickerAndWait(inputElement) {
        return new Promise((resolve) => {
            let settled = false;

            const cleanup = () => {
                inputElement.removeEventListener('change', onChangeCapture);
                window.removeEventListener('focus', onWindowFocus, true);
            };
            const settle = (selected) => {
                if (settled) {
                    return;
                }
                settled = true;
                cleanup();
                resolve(Boolean(selected));
            };
            const onChangeCapture = (event) => {
                const selected = (event.target.files || []).length > 0;
                settle(selected);
            };
            const onWindowFocus = () => {
                setTimeout(() => {
                    const selected = (inputElement.files || []).length > 0;
                    if (!selected) {
                        settle(false);
                    }
                }, 160);
            };

            inputElement.addEventListener('change', onChangeCapture);
            window.addEventListener('focus', onWindowFocus, true);
            inputElement.click();
        });
    }

    getElementValue(elementId) {
        const element = document.getElementById(elementId);
        if (!element) {
            return '';
        }
        return element.value || '';
    }

    getOptionalValue(elementId) {
        const value = this.getElementValue(elementId).trim();
        return value || undefined;
    }

    getCheckboxValue(elementId) {
        const element = document.getElementById(elementId);
        if (!element) {
            return false;
        }
        return Boolean(element.checked);
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new FeishuImportApp();
});
