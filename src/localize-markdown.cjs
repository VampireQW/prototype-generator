/* 从锁定安装包提取运行资源，不修改第三方源码。 */
const fs = require('node:fs');
const path = require('node:path');
const targetRoot = path.join(__dirname, 'vendor');
const source = process.argv[2] ? path.resolve(process.argv[2]) : targetRoot;
const files = {
    vditor: ['LICENSE', 'package.json', 'dist/index.min.js', 'dist/index.css',
        'dist/js/lute/lute.min.js', 'dist/js/i18n/zh_CN.js', 'dist/js/icons/ant.js',
        'dist/css/content-theme/light.css', 'dist/css/content-theme/dark.css'],
    dompurify: ['LICENSE', 'package.json', 'dist/purify.min.js']
};
for (const [pkg, names] of Object.entries(files)) {
    for (const name of names) {
        const target = path.join(targetRoot, pkg, name);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.copyFileSync(path.join(source, 'node_modules', pkg, name), target);
    }
}
if (source !== targetRoot) {
    for (const name of ['package.json', 'package-lock.json']) fs.copyFileSync(path.join(source, name), path.join(targetRoot, name));
}
console.log('已本地化工作台 Markdown 依赖与许可证。');
