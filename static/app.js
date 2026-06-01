const dropzone = document.querySelector('#dropzone');
const fileInput = document.querySelector('#fileInput');
const originalPreview = document.querySelector('#originalPreview');
const finalPreview = document.querySelector('#finalPreview');
const upscaleButton = document.querySelector('#upscaleButton');
const previewButton = document.querySelector('#previewButton');
const downloadButton = document.querySelector('#downloadButton');
const previewBackground = document.querySelector('#previewBackground');
const previews = document.querySelectorAll('.preview');
const statusMessage = document.querySelector('#status');
const metadata = document.querySelector('#metadata');

let selectedFile = null;
let originalObjectUrl = null;
let finalObjectUrl = null;

function setStatus(message) {
  statusMessage.textContent = message;
}

function revokeUrl(url) {
  if (url) URL.revokeObjectURL(url);
}

function setSelectedFile(file) {
  if (!file) return;
  selectedFile = file;
  revokeUrl(originalObjectUrl);
  originalObjectUrl = URL.createObjectURL(file);
  originalPreview.src = originalObjectUrl;
  finalPreview.removeAttribute('src');
  revokeUrl(finalObjectUrl);
  finalObjectUrl = null;
  previewButton.removeAttribute('href');
  previewButton.classList.add('disabled');
  downloadButton.removeAttribute('href');
  downloadButton.classList.add('disabled');
  metadata.textContent = '';
  upscaleButton.disabled = false;
  setStatus(`Ready: ${file.name}`);
}

function applyPreviewBackground() {
  previews.forEach((preview) => {
    preview.classList.remove('checkerboard', 'black', 'white');
    preview.classList.add(previewBackground.value);
  });
}

function appendField(formData, id, name = id) {
  const element = document.querySelector(`#${id}`);
  if (element.type === 'checkbox') {
    formData.append(name, element.checked ? 'true' : 'false');
  } else {
    formData.append(name, element.value);
  }
}

async function upscale() {
  if (!selectedFile) return;
  upscaleButton.disabled = true;
  setStatus('Processing locally on the server...');

  const formData = new FormData();
  formData.append('file', selectedFile);
  appendField(formData, 'width');
  appendField(formData, 'height');
  appendField(formData, 'dpi');
  appendField(formData, 'threshold');
  appendField(formData, 'neutralityTolerance', 'neutrality_tolerance');
  appendField(formData, 'interpolation');
  appendField(formData, 'compressionLevel', 'compression_level');
  appendField(formData, 'keepAspectRatio', 'keep_aspect_ratio');
  appendField(formData, 'transparentPadding', 'transparent_padding');
  appendField(formData, 'mildSharpening', 'mild_sharpening');

  try {
    const response = await fetch('/upscale', { method: 'POST', body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Upscale failed');

    const imageResponse = await fetch(result.download_url);
    const blob = await imageResponse.blob();
    revokeUrl(finalObjectUrl);
    finalObjectUrl = URL.createObjectURL(blob);
    finalPreview.src = finalObjectUrl;
    previewButton.href = result.preview_url;
    previewButton.classList.remove('disabled');
    downloadButton.href = result.download_url;
    downloadButton.classList.remove('disabled');
    const { width, height, original_width: originalWidth, original_height: originalHeight } = result.metadata;
    metadata.textContent = JSON.stringify(result.metadata, null, 2);
    setStatus(`Done. Output is ${width} × ${height}px from ${originalWidth} × ${originalHeight}px. Open Preview to inspect it before publishing.`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    upscaleButton.disabled = false;
  }
}

dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' || event.key === ' ') fileInput.click();
});
dropzone.addEventListener('dragover', (event) => {
  event.preventDefault();
  dropzone.classList.add('dragover');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', (event) => {
  event.preventDefault();
  dropzone.classList.remove('dragover');
  setSelectedFile(event.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => setSelectedFile(fileInput.files[0]));
previewBackground.addEventListener('change', applyPreviewBackground);
upscaleButton.addEventListener('click', upscale);

applyPreviewBackground();
