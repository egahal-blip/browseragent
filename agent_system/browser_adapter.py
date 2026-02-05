"""
Browser Adapter - Adapter for browser-use integration.

Maintains compatibility with browser-use Agent while providing
an interface for our multi-agent system.

NOTE: browser-use uses a callback-based approach where elements
are passed through step callbacks rather than direct state access.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import logging

from browser_use import BrowserSession, BrowserProfile
from browser_use.browser.views import BrowserStateSummary

logger = logging.getLogger(__name__)


@dataclass
class BrowserState:
    """Current browser state for our agents."""

    url: str
    title: str
    screenshot: Optional[str] = None
    dom_content: Optional[str] = None
    clickable_elements: List[Dict[str, Any]] = field(default_factory=list)
    input_elements: List[Dict[str, Any]] = field(default_factory=list)
    is_modal_present: bool = False
    modal_elements: List[Dict[str, Any]] = field(default_factory=list)
    viewport_width: int = 1920
    viewport_height: int = 1080
    scroll_position: int = 0
    max_scroll_position: int = 0
    # Additional info from browser-use
    pixels_above: int = 0
    pixels_below: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "screenshot": self.screenshot,
            "dom_content": self.dom_content,
            "clickable_elements": self.clickable_elements,
            "input_elements": self.input_elements,
            "is_modal_present": self.is_modal_present,
            "modal_elements": self.modal_elements,
            "viewport_width": self.viewport_width,
            "viewport_height": self.viewport_height,
            "scroll_position": self.scroll_position,
            "max_scroll_position": self.max_scroll_position,
            "pixels_above": self.pixels_above,
            "pixels_below": self.pixels_below,
        }

    @classmethod
    def from_browser_state_summary(
        cls,
        state: BrowserStateSummary,
        url: str,
        title: str,
        elements: List[Dict[str, Any]] = None,
    ) -> "BrowserState":
        """Create BrowserState from browser-use BrowserStateSummary."""
        return cls(
            url=url,
            title=title,
            screenshot=state.screenshot,
            pixels_above=state.pixels_above or 0,
            pixels_below=state.pixels_below or 0,
            clickable_elements=elements or [],
        )


@dataclass
class BrowserAction:
    """An action to execute in the browser."""

    action_type: str  # click, type, scroll, wait, etc.
    element_index: Optional[int] = None
    text: Optional[str] = None
    coordinate: Optional[tuple[int, int]] = None
    scroll_direction: Optional[str] = None
    scroll_amount: Optional[int] = None
    wait_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "element_index": self.element_index,
            "text": self.text,
            "coordinate": self.coordinate,
            "scroll_direction": self.scroll_direction,
            "scroll_amount": self.scroll_amount,
            "wait_time": self.wait_time,
        }


@dataclass
class ActionResult:
    """Result of a browser action."""

    success: bool
    action: BrowserAction
    error: Optional[str] = None
    new_state: Optional[BrowserState] = None
    execution_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action.to_dict(),
            "error": self.error,
            "execution_time": self.execution_time,
        }


class BrowserAdapter:
    """
    Adapter for browser-use integration.

    Since browser-use uses a callback-based approach, this adapter
    stores state from callbacks and provides it to our agents.
    """

    def __init__(
        self,
        browser_session: BrowserSession,
        debug: bool = False,
    ):
        self.browser_session = browser_session
        self.debug = debug
        self._logger = logging.getLogger("BrowserAdapter")

        if debug:
            self._logger.setLevel(logging.DEBUG)

        # Track state - updated via callback from browser-use agent
        self._current_state: Optional[BrowserState] = None
        self._action_history: List[ActionResult] = []
        self._current_elements: List[Dict[str, Any]] = []

    async def update_from_callback(
        self,
        browser_state: BrowserStateSummary,
        agent_output: Any,
        step: int,
    ) -> None:
        """
        Update state from browser-use callback.

        This method is called by the step callback from browser-use Agent.
        """
        try:
            url = await self.browser_session.get_current_page_url() or ""

            # Store elements from agent output for our agents to use
            if hasattr(agent_output, 'action') and hasattr(agent_output.action, 'index'):
                # Track which element was interacted with
                pass

            self._current_state = BrowserState.from_browser_state_summary(
                browser_state,
                url,
                "",  # title will be updated separately
                self._current_elements,
            )

            self._logger.debug(f"Updated state from callback step {step}: {url}")

        except Exception as e:
            self._logger.error(f"Error updating from callback: {e}")

    def set_elements(self, elements: List[Dict[str, Any]]) -> None:
        """
        Set current clickable elements.

        This should be called from the step callback with elements
        extracted from the browser-use agent context.
        """
        self._current_elements = elements
        if self._current_state:
            self._current_state.clickable_elements = elements

    async def get_state(self) -> BrowserState:
        """
        Get current browser state.

        Returns the last state updated via callback.
        """
        if self._current_state is None:
            # Return empty state if not yet initialized
            return BrowserState(url="", title="")

        return self._current_state

    async def execute_action(self, action: BrowserAction) -> ActionResult:
        """
        Execute an action in the browser.

        Note: This is a stub for future implementation.
        Currently actions are executed by browser-use Agent directly.
        """
        import time

        start_time = time.time()

        self._logger.warning(
            "Direct action execution not yet implemented. "
            "Actions should be executed by browser-use Agent."
        )

        execution_time = time.time() - start_time

        return ActionResult(
            success=False,
            action=action,
            error="Direct action execution not implemented - use browser-use Agent",
            execution_time=execution_time,
        )

    def get_action_history(self) -> List[ActionResult]:
        """Get history of executed actions."""
        return self._action_history.copy()

    def clear_action_history(self) -> None:
        """Clear action history."""
        self._action_history.clear()


async def create_browser_session(
    headless: bool = False,
    user_data_dir: Optional[Path] = None,
    keep_alive: bool = True,
) -> BrowserSession:
    """
    Create a browser session with the given configuration.

    Args:
        headless: Whether to run browser in headless mode
        user_data_dir: Directory for user data (persistent session)
        keep_alive: Keep browser alive after session ends

    Returns:
        BrowserSession instance
    """
    browser_profile = BrowserProfile(
        headless=headless,
        user_data_dir=user_data_dir or str(Path.home() / ".browser-agent" / "profile"),
        keep_alive=keep_alive,
    )

    return BrowserSession(browser_profile=browser_profile)
