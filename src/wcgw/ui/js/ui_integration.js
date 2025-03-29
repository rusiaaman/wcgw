/**
 * Integration helpers for token counter UI
 */

import {
  initializeTokenCounter,
  updateTokenCounter,
  handleAutoContinue,
} from "./token_counter.js";

/**
 * Initialize and integrate token counter with existing UI
 */
export function integrateTokenCounter() {
  // Initialize token counter
  const tokenCounter = initializeTokenCounter();

  // Set up response handler
  setupResponseHandler(tokenCounter);

  return tokenCounter;
}

/**
 * Set up response handler to update token counter
 * @param {HTMLElement} tokenCounter - The token counter element
 */
function setupResponseHandler(tokenCounter) {
  // Try to find the original response handler
  // This is a non-invasive approach that works with different UI architectures

  // Method 1: Monkey patch fetch API (common approach for web UIs)
  const originalFetch = window.fetch;
  window.fetch = async function (url, options) {
    const response = await originalFetch.apply(this, arguments);

    // Clone the response to avoid consuming the stream
    const clone = response.clone();

    try {
      // Check if this is a Claude API response
      if (url.includes("/api/claude") || url.includes("/v1/messages")) {
        const data = await clone.json();

        // Update token counter if token_usage is present
        if (data && data.token_usage) {
          updateTokenCounter(tokenCounter, data.token_usage);
          handleAutoContinue(data);
        }
      }
    } catch (e) {
      // Ignore errors in our monitoring code
      console.warn("Error monitoring API response:", e);
    }

    return response;
  };

  // Method 2: Observer pattern for UI updates
  // This is useful when we can't intercept the API directly
  setupResponseObserver((response) => {
    if (response && response.token_usage) {
      updateTokenCounter(tokenCounter, response.token_usage);
      handleAutoContinue(response);
    }
  });
}

/**
 * Set up an observer to watch for Claude responses
 * @param {Function} callback - Function to call when a response is detected
 */
export function setupResponseObserver(callback) {
  // Create a MutationObserver to watch for new messages
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.addedNodes.length) {
        // Look for assistant messages that were just added
        const assistantMessages = Array.from(mutation.addedNodes).filter(
          (node) =>
            node.classList && node.classList.contains("assistant-message"),
        );

        if (assistantMessages.length) {
          // When we see a new assistant message, check for token usage in the response
          checkForTokenUsage(callback);
        }
      }
    }
  });

  // Start observing the messages container
  const messagesContainer = document.querySelector(".messages-container");
  if (messagesContainer) {
    observer.observe(messagesContainer, { childList: true, subtree: true });
  }
}

/**
 * Check for token usage data in the most recent response
 * @param {Function} callback - Function to call with the response data
 */
function checkForTokenUsage(callback) {
  // In a real implementation, this would access the actual response data
  // For now, we'll simulate this with a data attribute or global variable

  // Method 1: Check for data attribute on the message
  const latestMessage = document.querySelector(".assistant-message:last-child");
  if (latestMessage && latestMessage.dataset.tokenUsage) {
    try {
      const tokenUsage = JSON.parse(latestMessage.dataset.tokenUsage);
      callback({ token_usage: tokenUsage });
    } catch (e) {
      console.warn("Error parsing token usage data:", e);
    }
  }

  // Method 2: Check for global response cache
  if (window.__lastClaudeResponse && window.__lastClaudeResponse.token_usage) {
    callback(window.__lastClaudeResponse);
  }
}

/**
 * Helper to store the last Claude response in a global variable
 * This should be called in your API handling code
 * @param {Object} response - The Claude API response
 */
export function storeLastResponse(response) {
  window.__lastClaudeResponse = response;
}
