# Phase 3: Per-client agent logic goes here.

# TODO Phase 1A: Before passing inbound message to intent parser, call:
#   from firewall.input_guard import scan_input
#   result = scan_input(message, phone, is_admin)
#   if result.action != "pass":
#       send(result.redirect_message or BLOCK_GENERIC_RESPONSE)
#       return

# TODO Phase 1A: Before sending response to user, call:
#   from firewall.output_guard import scan_output
#   result = scan_output(response, phone, tool_calls_made)
#   if result.action != "pass":
#       send(result.redirect_message or BLOCK_GENERIC_RESPONSE)
#       return
