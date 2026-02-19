class FeishuImportApp {
    constructor() {
        this.initElements();
        this.bindEvents();
        this.loadConfig();
        this.setupMockData();
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
        this.$browseBtn.addEventListener('click', () => this.browseFolder());
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
        if (config) {
            const parsed = JSON.parse(config);
            Object.keys(parsed).forEach(key => {
                const element = document.getElementById(key);
                if (element) {
                    if (element.type === 'checkbox') {
                        element.checked = parsed[key];
                    } else {
                        element.value = parsed[key];
                    }
                }
            });
            this.addLog('配置已加载', 'info');
        }
    }

    saveConfig() {
        const config = {
            feishuAppId: document.getElementById('feishuAppId').value,
            feishuAppSecret: document.getElementById('feishuAppSecret').value,
            feishuFolderToken: document.getElementById('feishuFolderToken').value,
            feishuWebhookUrl: document.getElementById('feishuWebhookUrl').value
        };

        localStorage.setItem('feishuImportConfig', JSON.stringify(config));
        this.hideConfig();
        this.showToast('配置已保存', 'success');
        this.addLog('应用配置已保存', 'success');
    }

    runImport() {
        if (!this.validateForm()) {
            return;
        }

        this.$runBtn.disabled = true;
        this.$runBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 导入中...';
        this.clearLog();
        this.updateStatus(0, 0, 0, 0);

        this.addLog('任务开始', 'info');
        this.simulateImportProcess();
    }

    validateForm() {
        const source = this.$localBtn.classList.contains('active') ? 'local' : 'github';

        if (source === 'local') {
            const localPath = document.getElementById('localPath').value.trim();
            if (!localPath) {
                this.showToast('请选择本地目录路径', 'error');
                return false;
            }
        } else {
            const githubRepo = document.getElementById('githubRepo').value.trim();
            if (!githubRepo) {
                this.showToast('请输入 GitHub 仓库地址', 'error');
                return false;
            }
        }

        return true;
    }

    async simulateImportProcess() {
        const steps = [
            { msg: '初始化源适配器', delay: 500 },
            { msg: '解析源文件结构', delay: 800 },
            { msg: '发现 15 个 Markdown 文件', delay: 600 },
            { msg: '创建文档编排计划', delay: 700 },
            { msg: '开始处理文档：01-简介.md', delay: 1000 },
            { msg: '成功上传图片：architecture.png', delay: 400 },
            { msg: '文档 01-简介.md 导入成功', delay: 500 },
            { msg: '开始处理文档：02-快速开始.md', delay: 900 },
            { msg: '自动处理表格块', delay: 300 },
            { msg: '文档 02-快速开始.md 导入成功', delay: 500 },
            { msg: '开始处理文档：03-API 参考.md', delay: 1200 },
            { msg: '转换代码块为飞书格式', delay: 400 },
            { msg: '文档 03-API 参考.md 导入成功', delay: 500 },
            { msg: '处理媒体文件上传', delay: 600 },
            { msg: '生成导航文档', delay: 800 },
            { msg: '任务执行完成', delay: 300 }
        ];

        let processed = 0;
        const total = 15;

        for (let i = 0; i < steps.length; i++) {
            const step = steps[i];
            await this.delay(step.delay);

            if (step.msg.includes('导入成功')) {
                processed++;
                this.updateStatus(total, processed, 0, 0);
            }

            this.addLog(step.msg, this.getLogType(step.msg));
        }

        const failed = 1;
        const skipped = 2;
        this.updateStatus(total, processed - failed - skipped, failed, skipped);

        await this.delay(500);
        this.showToast(`任务完成！成功导入 ${processed - failed - skipped} 个文档，失败 ${failed} 个，跳过 ${skipped} 个`, 'success');

        this.$runBtn.disabled = false;
        this.$runBtn.innerHTML = '<i class="fas fa-play"></i> 开始导入';
    }

    getLogType(msg) {
        if (msg.includes('成功') || msg.includes('完成')) {
            return 'success';
        } else if (msg.includes('失败') || msg.includes('错误')) {
            return 'error';
        } else if (msg.includes('自动处理') || msg.includes('跳过')) {
            return 'warning';
        } else {
            return 'info';
        }
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

    browseFolder() {
        const path = prompt('请输入本地目录路径', '/path/to/docs');
        if (path) {
            document.getElementById('localPath').value = path;
            this.addLog(`已选择目录：${path}`, 'info');
        }
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

    setupMockData() {
        const mockConfig = {
            feishuAppId: 'cli_a1b2c3d4e5f6g7h8',
            feishuAppSecret: '********************************',
            feishuFolderToken: 'fld1234567890abcdef1234567890abcdef',
            feishuWebhookUrl: ''
        };

        localStorage.setItem('feishuImportConfig', JSON.stringify(mockConfig));
        this.loadConfig();
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new FeishuImportApp();
});