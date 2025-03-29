/**
 * Token counter UI components for Claude Desktop
 */

/**
 * Initialize token counter UI element
 * @returns {HTMLElement} The token counter element
 */
export function initializeTokenCounter() {
  // Create token counter element
  const tokenCounter = document.createElement("div");
  tokenCounter.className = "token-counter";
  tokenCounter.style.marginRight = "12px";
  tokenCounter.style.fontSize = "12px";
  tokenCounter.style.color = "var(--text-secondary, #8c8c8c)";
  tokenCounter.style.display = "flex";
  tokenCounter.style.alignItems = "center";

  // Set initial content
  tokenCounter.innerHTML = `
    <span class="token-count-total">0</span> /
    <span class="token-max-size-kb">100</span> KB
  `;

  // Find input area
  const inputArea = document.querySelector(".chat-input-container");
  if (!inputArea) {
    console.warn("Could not find chat input container");
    return tokenCounter;
  }

  const sendButton = inputArea.querySelector(".send-button");
  if (!sendButton || !sendButton.parentNode) {
    console.warn("Could not find send button");
    // Add at the end of input area as fallback
    inputArea.appendChild(tokenCounter);
  } else {
    // Insert before send button
    sendButton.parentNode.insertBefore(tokenCounter, sendButton);
  }

  return tokenCounter;
}

/**
 * Update token counter with usage information
 * @param {HTMLElement} tokenCounter - The token counter element
 * @param {Object} tokenUsage - Token usage information from the API
 */
export function updateTokenCounter(tokenCounter, tokenUsage) {
  if (!tokenCounter || !tokenUsage) return;

  // Update content with KB format
  tokenCounter.innerHTML = `
    <span class="token-count-total">${tokenUsage.total_tokens_kb}</span> /
    <span class="token-max-size-kb">${tokenUsage.token_max_size_kb}</span> KB
  `;

  // Change color based on usage percentage
  const usagePercentage = tokenUsage.usage_percentage;

  if (usagePercentage > 0.9) {
    tokenCounter.style.color = "var(--text-error, #ff4d4f)";
  } else if (usagePercentage > 0.7) {
    tokenCounter.style.color = "var(--text-warning, #faad14)";
  } else {
    tokenCounter.style.color = "var(--text-secondary, #8c8c8c)";
  }
}

/**
 * Handle auto-continue notification
 * @param {Object} response - Response from the API
 */
export function handleAutoContinue(response) {
  if (!response || !response.auto_continued) return;

  // Show auto-continue notification
  const notification = document.createElement("div");
  notification.className = "auto-continue-notification";
  notification.style.padding = "4px 8px";
  notification.style.marginBottom = "8px";
  notification.style.backgroundColor = "var(--background-secondary, #f0f0f0)";
  notification.style.borderRadius = "4px";
  notification.style.fontSize = "12px";
  notification.style.color = "var(--text-secondary, #8c8c8c)";
  notification.textContent = "Auto-continuing response...";

  // Add to message container
  const messageContainer = document.querySelector(".messages-container");
  if (!messageContainer) {
    console.warn("Could not find messages container");
    return;
  }

  messageContainer.appendChild(notification);

  // Remove after 3 seconds
  setTimeout(() => {
    notification.remove();
  }, 3000);
}
