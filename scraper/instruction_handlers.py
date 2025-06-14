"""
Instruction handlers implementing the Command pattern.
Each handler executes specific instruction types.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .config_schema import (
    Instruction, WaitCondition, ClickInstruction, WaitInstruction,
    LoopInstruction, IfInstruction, CollectInstruction, NavigateInstruction,
    InputInstruction, SelectInstruction, ScrollInstruction
)

logger = logging.getLogger(__name__)


class InstructionContext:
    """Context object passed between instruction handlers."""

    def __init__(self, page: Page, variables: Optional[Dict[str, Any]] = None):
        self.page = page
        self.variables = variables or {}
        self.collected_data: Dict[str, List[Dict[str, Any]]] = {}
        self.loop_counters: Dict[str, int] = {}
        self.metadata: Dict[str, Any] = {}


class InstructionHandler(ABC):
    """Abstract base class for instruction handlers."""

    def __init__(self):
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    @abstractmethod
    async def execute(self, instruction: Instruction, context: InstructionContext) -> bool:
        """
        Execute the instruction.

        Args:
            instruction: The instruction to execute
            context: The execution context

        Returns:
            bool: True if execution was successful, False otherwise
        """
        pass

    async def handle_wait_condition(self, condition: WaitCondition, context: InstructionContext) -> bool:
        """Handle a wait condition."""
        try:
            if condition.type == "timeout":
                await asyncio.sleep(condition.value / 1000.0)  # Convert ms to seconds
                return True

            elif condition.type == "selector":
                await context.page.wait_for_selector(
                    condition.value,
                    timeout=condition.timeout_ms,
                    state="visible"
                )
                return True

            elif condition.type == "url_contains":
                current_url = context.page.url
                return condition.value in current_url

            elif condition.type == "element_count":
                count = len(await context.page.query_selector_all(condition.value))
                return count > 0

            return False

        except PlaywrightTimeoutError:
            self.logger.warning(f"Wait condition timed out: {condition}")
            return False
        except Exception as e:
            self.logger.error(f"Error in wait condition: {e}")
            return False


class ClickHandler(InstructionHandler):
    """Handler for click instructions."""

    async def execute(self, instruction: ClickInstruction, context: InstructionContext) -> bool:
        """Execute click instruction."""
        try:
            self.logger.info(f"Executing click on: {instruction.selector}")

            if instruction.all_matching:
                # Click all matching elements
                elements = await context.page.query_selector_all(instruction.selector)
                if not elements and not instruction.optional:
                    self.logger.error(f"No elements found for selector: {instruction.selector}")
                    return False

                clicked_count = 0
                for element in elements:
                    try:
                        if await element.is_visible():
                            await element.click()
                            clicked_count += 1
                            await asyncio.sleep(0.5)  # Small delay between clicks
                    except Exception as e:
                        self.logger.warning(f"Failed to click element: {e}")
                        if not instruction.optional:
                            continue

                self.logger.info(f"Clicked {clicked_count} elements")

            else:
                # Click single element
                try:
                    await context.page.click(instruction.selector, timeout=10000)
                except PlaywrightTimeoutError:
                    if not instruction.optional:
                        self.logger.error(f"Element not found or not clickable: {instruction.selector}")
                        return False
                    self.logger.warning(f"Optional click failed: {instruction.selector}")

            # Handle wait condition after click
            if instruction.wait_after:
                await self.handle_wait_condition(instruction.wait_after, context)

            return True

        except Exception as e:
            self.logger.error(f"Error executing click instruction: {e}")
            return not instruction.optional


class WaitHandler(InstructionHandler):
    """Handler for wait instructions."""

    async def execute(self, instruction: WaitInstruction, context: InstructionContext) -> bool:
        """Execute wait instruction."""
        self.logger.info(f"Executing wait: {instruction.condition}")
        return await self.handle_wait_condition(instruction.condition, context)


class LoopHandler(InstructionHandler):
    """Handler for loop instructions."""

    def __init__(self, instruction_executor):
        super().__init__()
        self.instruction_executor = instruction_executor

    async def execute(self, instruction: LoopInstruction, context: InstructionContext) -> bool:
        """Execute loop instruction."""
        self.logger.info(f"Executing loop: {instruction.iterator}")

        loop_id = f"loop_{id(instruction)}"
        context.loop_counters[loop_id] = 0

        try:
            if instruction.iterator == "pagination":
                return await self._handle_pagination_loop(instruction, context, loop_id)
            elif instruction.iterator == "dropdown_options":
                return await self._handle_dropdown_loop(instruction, context, loop_id)
            elif instruction.iterator == "count":
                return await self._handle_count_loop(instruction, context, loop_id)
            elif instruction.iterator == "while":
                return await self._handle_while_loop(instruction, context, loop_id)
            else:
                self.logger.error(f"Unknown loop iterator: {instruction.iterator}")
                return False

        except Exception as e:
            self.logger.error(f"Error in loop execution: {e}")
            return False

    async def _handle_pagination_loop(self, instruction: LoopInstruction, context: InstructionContext,
                                      loop_id: str) -> bool:
        """Handle pagination loop."""
        if not instruction.next_selector:
            self.logger.error("Pagination loop requires next_selector")
            return False

        while context.loop_counters[loop_id] < instruction.max_iterations:
            # Execute loop instructions
            for loop_instruction in instruction.instructions:
                await self.instruction_executor.execute_instruction(loop_instruction, context)

            # Check break condition
            if instruction.break_condition:
                if await self.handle_wait_condition(instruction.break_condition, context):
                    self.logger.info("Break condition met, exiting loop")
                    break

            # Try to click next button
            try:
                next_button = await context.page.query_selector(instruction.next_selector)
                if not next_button:
                    self.logger.info("Next button not found, ending pagination")
                    break

                if not await next_button.is_enabled():
                    self.logger.info("Next button disabled, ending pagination")
                    break

                await next_button.click()
                await asyncio.sleep(2)  # Wait for page to load

                context.loop_counters[loop_id] += 1

            except Exception as e:
                self.logger.info(f"Pagination ended: {e}")
                break

        return True

    async def _handle_dropdown_loop(self, instruction: LoopInstruction, context: InstructionContext,
                                    loop_id: str) -> bool:
        """Handle dropdown options loop."""
        if not instruction.dropdown_selector:
            self.logger.error("Dropdown loop requires dropdown_selector")
            return False

        try:
            # Get all options
            options = await context.page.query_selector_all(f"{instruction.dropdown_selector} option")

            start_index = 1 if instruction.skip_first_option else 0

            for i, option in enumerate(options[start_index:], start_index):
                if context.loop_counters[loop_id] >= instruction.max_iterations:
                    break

                # Select option
                option_value = await option.get_attribute("value")
                await context.page.select_option(instruction.dropdown_selector, value=option_value)

                # Store current option in context
                context.variables['current_option_index'] = i
                context.variables['current_option_value'] = option_value
                context.variables['current_option_text'] = await option.text_content()

                # Execute loop instructions
                for loop_instruction in instruction.instructions:
                    await self.instruction_executor.execute_instruction(loop_instruction, context)

                context.loop_counters[loop_id] += 1
                await asyncio.sleep(1)  # Small delay between options

            return True

        except Exception as e:
            self.logger.error(f"Error in dropdown loop: {e}")
            return False

    async def _handle_count_loop(self, instruction: LoopInstruction, context: InstructionContext, loop_id: str) -> bool:
        """Handle count-based loop."""
        if not instruction.count:
            self.logger.error("Count loop requires count parameter")
            return False

        for i in range(instruction.count):
            if context.loop_counters[loop_id] >= instruction.max_iterations:
                break

            context.variables['loop_index'] = i

            # Execute loop instructions
            for loop_instruction in instruction.instructions:
                await self.instruction_executor.execute_instruction(loop_instruction, context)

            context.loop_counters[loop_id] += 1

        return True

    async def _handle_while_loop(self, instruction: LoopInstruction, context: InstructionContext, loop_id: str) -> bool:
        """Handle while loop."""
        if not instruction.while_condition:
            self.logger.error("While loop requires while_condition")
            return False

        while context.loop_counters[loop_id] < instruction.max_iterations:
            # Check while condition
            if not await self.handle_wait_condition(instruction.while_condition, context):
                self.logger.info("While condition no longer met, exiting loop")
                break

            # Execute loop instructions
            for loop_instruction in instruction.instructions:
                await self.instruction_executor.execute_instruction(loop_instruction, context)

            context.loop_counters[loop_id] += 1
            await asyncio.sleep(0.5)  # Small delay to prevent tight loop

        return True


class IfHandler(InstructionHandler):
    """Handler for conditional instructions."""

    def __init__(self, instruction_executor):
        super().__init__()
        self.instruction_executor = instruction_executor

    async def execute(self, instruction: IfInstruction, context: InstructionContext) -> bool:
        """Execute conditional instruction."""
        self.logger.info(f"Executing if condition: {instruction.condition}")

        try:
            condition_met = await self.handle_wait_condition(instruction.condition, context)

            if condition_met:
                self.logger.info("Condition met, executing then instructions")
                for then_instruction in instruction.then_instructions:
                    await self.instruction_executor.execute_instruction(then_instruction, context)
            else:
                self.logger.info("Condition not met, executing else instructions")
                for else_instruction in instruction.else_instructions:
                    await self.instruction_executor.execute_instruction(else_instruction, context)

            return True

        except Exception as e:
            self.logger.error(f"Error in conditional instruction: {e}")
            return False


class CollectHandler(InstructionHandler):
    """Handler for data collection instructions."""

    async def execute(self, instruction: CollectInstruction, context: InstructionContext) -> bool:
        """Execute collect instruction."""
        self.logger.info(f"Executing collect: {instruction.name}")

        try:
            # Find container elements
            containers = await context.page.query_selector_all(instruction.container_selector)
            if not containers:
                self.logger.warning(f"No containers found for selector: {instruction.container_selector}")
                return True  # Not necessarily an error

            collected_items = []

            for container in containers:
                # Find items within container
                items = await container.query_selector_all(instruction.item_selector)

                for item in items:
                    if instruction.limit and len(collected_items) >= instruction.limit:
                        break

                    # Extract fields from item
                    item_data = {}
                    for field_name, field_config in instruction.fields.items():
                        try:
                            value = await self._extract_field(item, field_config)
                            item_data[field_name] = value
                        except Exception as e:
                            self.logger.warning(f"Error extracting field {field_name}: {e}")
                            item_data[field_name] = field_config.default or ""

                    collected_items.append(item_data)

                if instruction.limit and len(collected_items) >= instruction.limit:
                    break

            # Store collected data
            context.collected_data[instruction.name] = collected_items
            self.logger.info(f"Collected {len(collected_items)} items for {instruction.name}")

            return True

        except Exception as e:
            self.logger.error(f"Error in collect instruction: {e}")
            return False

    async def _extract_field(self, element, field_config) -> str:
        """Extract field value from element."""
        try:
            if isinstance(field_config.selector, list):
                # Try multiple selectors
                for selector in field_config.selector:
                    try:
                        target = await element.query_selector(selector)
                        if target:
                            break
                    except:
                        continue
                else:
                    return field_config.default or ""
            else:
                target = await element.query_selector(field_config.selector)

            if not target:
                return field_config.default or ""

            # Extract value based on attribute
            if field_config.attribute == "text":
                value = await target.text_content() or ""
            else:
                value = await target.get_attribute(field_config.attribute) or ""

            # Apply processors if configured
            # (Processor implementation would go here)

            return value.strip()

        except Exception as e:
            self.logger.warning(f"Error extracting field: {e}")
            return field_config.default or ""


class NavigateHandler(InstructionHandler):
    """Handler for navigation instructions."""

    async def execute(self, instruction: NavigateInstruction, context: InstructionContext) -> bool:
        """Execute navigate instruction."""
        self.logger.info(f"Executing navigate to: {instruction.url}")

        try:
            await context.page.goto(instruction.url, wait_until='domcontentloaded', timeout=30000)

            if instruction.wait_after:
                await self.handle_wait_condition(instruction.wait_after, context)

            return True

        except Exception as e:
            self.logger.error(f"Error navigating to {instruction.url}: {e}")
            return False


class InputHandler(InstructionHandler):
    """Handler for input instructions."""

    async def execute(self, instruction: InputInstruction, context: InstructionContext) -> bool:
        """Execute input instruction."""
        self.logger.info(f"Executing input on: {instruction.selector}")

        try:
            if instruction.clear_first:
                await context.page.fill(instruction.selector, "")

            await context.page.type(instruction.selector, instruction.value)

            return True

        except Exception as e:
            self.logger.error(f"Error in input instruction: {e}")
            return False


class SelectHandler(InstructionHandler):
    """Handler for select instructions."""

    async def execute(self, instruction: SelectInstruction, context: InstructionContext) -> bool:
        """Execute select instruction."""
        self.logger.info(f"Executing select on: {instruction.selector}")

        try:
            if instruction.value is not None:
                await context.page.select_option(instruction.selector, value=instruction.value)
            elif instruction.text is not None:
                await context.page.select_option(instruction.selector, label=instruction.text)
            elif instruction.index is not None:
                await context.page.select_option(instruction.selector, index=instruction.index)
            else:
                self.logger.error("Select instruction requires value, text, or index")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error in select instruction: {e}")
            return False


class ScrollHandler(InstructionHandler):
    """Handler for scroll instructions."""

    async def execute(self, instruction: ScrollInstruction, context: InstructionContext) -> bool:
        """Execute scroll instruction."""
        self.logger.info(f"Executing scroll: {instruction.direction}")

        try:
            if instruction.direction == "to_element" and instruction.selector:
                element = await context.page.query_selector(instruction.selector)
                if element:
                    await element.scroll_into_view_if_needed()
                else:
                    self.logger.warning(f"Element not found for scroll: {instruction.selector}")
                    return False

            elif instruction.direction == "down":
                amount = instruction.amount or 1000
                await context.page.evaluate(f"window.scrollBy(0, {amount})")

            elif instruction.direction == "up":
                amount = instruction.amount or 1000
                await context.page.evaluate(f"window.scrollBy(0, -{amount})")

            return True

        except Exception as e:
            self.logger.error(f"Error in scroll instruction: {e}")
            return False


class InstructionExecutor:
    """Main executor that coordinates instruction handlers."""

    def __init__(self):
        self.handlers = {
            'click': ClickHandler(),
            'wait': WaitHandler(),
            'loop': LoopHandler(self),
            'if': IfHandler(self),
            'collect': CollectHandler(),
            'navigate': NavigateHandler(),
            'input': InputHandler(),
            'select': SelectHandler(),
            'scroll': ScrollHandler()
        }
        self.logger = logging.getLogger(__name__)

    async def execute_instruction(self, instruction: Instruction, context: InstructionContext) -> bool:
        """Execute a single instruction."""
        instruction_type = instruction.type
        handler = self.handlers.get(instruction_type)

        if not handler:
            self.logger.error(f"No handler found for instruction type: {instruction_type}")
            return False

        try:
            return await handler.execute(instruction, context)
        except Exception as e:
            self.logger.error(f"Error executing instruction {instruction_type}: {e}")
            return False

    async def execute_instructions(self, instructions: List[Instruction], context: InstructionContext) -> bool:
        """Execute a list of instructions."""
        for instruction in instructions:
            success = await self.execute_instruction(instruction, context)
            if not success:
                self.logger.warning(f"Instruction failed but continuing: {instruction.type}")

        return True

    def register_handler(self, instruction_type: str, handler: InstructionHandler):
        """Register a custom instruction handler."""
        self.handlers[instruction_type] = handler