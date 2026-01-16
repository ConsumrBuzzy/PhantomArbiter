# Implementation Plan: Delta Neutral Engine Live Mode Integration

## Overview

This implementation plan focuses on completing the Web UI integration for the Delta Neutral Engine (Funding Engine). The backend infrastructure is already in place - we need to connect the frontend to display live market opportunities and enable position management.

**Existing Infrastructure:**
- ✅ FundingEngine with paper/live mode support
- ✅ DriftAdapter for protocol interaction
- ✅ SafetyGate for risk management
- ✅ WebSocket server with command handlers
- ✅ Base UI template (engine-drift.html)

**What We're Building:**
- Backend API for market data
- Frontend market display and refresh
- "Take Position" and "Leave Position" UI flows
- Real-time position updates via WebSocket

---

## Tasks

- [ ] 1. Backend API Enhancement
  - Enhance DriftFundingFeed to provide complete market data
  - Update /api/drift/markets endpoint
  - Add caching and error handling
  - _Requirements: 2.1, 2.2, 2.6_

- [ ] 1.1 Create FundingMarket dataclass
  - Add dataclass with fields: symbol, rate_1h, rate_8h, apr, direction, open_interest, volume_24h
  - _Requirements: 2.2_

- [ ] 1.2 Implement get_funding_markets() method
  - Query Drift Protocol for all perp markets
  - Calculate APR from 8h rate (rate_8h × 3 × 365)
  - Determine direction (positive rate = shorts receive)
  - _Requirements: 2.2, 2.6_

- [ ] 1.3 Implement get_market_stats() method
  - Calculate total open interest across all markets
  - Calculate total 24h volume
  - Calculate average funding rate
  - _Requirements: 2.2_

- [ ] 1.4 Add response caching (5-minute TTL)
  - Cache market data to reduce RPC calls
  - Invalidate cache on manual refresh
  - _Requirements: 2.8_

- [ ] 1.5 Update /api/drift/markets endpoint
  - Use enhanced DriftFundingFeed
  - Return JSON with markets array and stats object
  - Add error handling for RPC failures
  - _Requirements: 2.1, 2.2_

- [ ] 1.6 Write unit tests for DriftFundingFeed
  - Test market data parsing
  - Test APR calculation
  - Test stats aggregation
  - _Requirements: 2.2_

- [ ] 1.7 Write property test for APR calculation
  - **Property 26: Revenue Calculation**
  - **Validates: Requirements 6.2**
  - For any funding rate R, APR should equal R × 3 × 365

- [ ] 2. Frontend Market Data Display
  - Implement market data fetching and rendering
  - Display funding rates table
  - Display opportunity cards
  - Update market stats
  - _Requirements: 2.1, 2.2, 2.9_

- [ ] 2.1 Implement fetchDriftMarkets() method
  - Add async method to DashboardApp class
  - Fetch from /api/drift/markets
  - Handle loading and error states
  - Call on page load and every 30 seconds
  - _Requirements: 2.1, 2.8_

- [ ] 2.2 Implement renderFundingTable(markets) method
  - Sort markets by APR (highest first)
  - Render table rows with all columns
  - Color-code positive (green) and negative (red) rates
  - Add "Take" button for each market
  - _Requirements: 2.2_

- [ ] 2.3 Implement renderOpportunityCards(opportunities) method
  - Filter top 3 opportunities by APR
  - Render opportunity cards with symbol, direction, APR
  - Add "Take Position" button to each card
  - _Requirements: 2.2_

- [ ] 2.4 Implement updateMarketStats(stats) method
  - Update total OI display
  - Update 24h volume display
  - Update average funding display
  - Format numbers with K/M/B suffixes
  - _Requirements: 2.2_

- [ ] 2.5 Add auto-refresh logic
  - Set interval to fetch markets every 30 seconds
  - Show "Last updated" timestamp
  - Add manual refresh button
  - _Requirements: 2.8, 2.9_

- [ ] 2.6 Write integration test for market display
  - Test data fetching
  - Test table rendering
  - Test opportunity cards
  - Test stats display
  - _Requirements: 2.1, 2.2_

- [ ] 3. Position Management UI - Take Position
  - Implement "Take Position" flow
  - Show position size input modal
  - Send DRIFT_OPEN_POSITION command
  - Handle responses
  - _Requirements: 4.1, 4.2, 4.7, 8.6_

- [x] 3.1 Create position size input modal
  - Add modal HTML to engine-drift.html
  - Include market name, direction, size input
  - Add min/max size validation
  - Add leverage display
  - _Requirements: 4.1, 4.2_

- [-] 3.2 Implement handleTakePosition(market, direction) method
  - Show position size modal
  - Pre-fill market and direction
  - Calculate suggested size based on available collateral
  - _Requirements: 4.1_

- [ ] 3.3 Implement confirmTakePosition() method
  - Validate size input (min: 0.005 SOL, max: available collateral)
  - Calculate expected leverage
  - Show confirmation with trade details
  - _Requirements: 4.2, 6.7_

- [ ] 3.4 Send DRIFT_OPEN_POSITION command
  - Build WebSocket command payload
  - Include market, direction, size
  - Show loading state on button
  - Disable all action buttons during execution
  - _Requirements: 4.3, 8.6_

- [ ] 3.5 Handle COMMAND_RESULT response
  - Show success toast with transaction signature
  - Show error toast with error message
  - Re-enable action buttons
  - Close modal on success
  - _Requirements: 8.8, 8.9_

- [ ] 3.6 Write property test for position size validation
  - **Property 9: Deposit Validation**
  - **Validates: Requirements 3.1**
  - For any size S and available collateral C, position should be accepted if 0.005 ≤ S ≤ C

- [ ] 4. Position Management UI - Leave Position
  - Implement "Leave Position" flow
  - Show confirmation modal
  - Send DRIFT_CLOSE_POSITION command
  - Handle responses
  - _Requirements: 4.8, 4.10, 4.12, 8.7_

- [ ] 4.1 Add "Leave" button to positions table
  - Add button to each position row
  - Show position details (market, size, PnL)
  - Disable if no position exists
  - _Requirements: 4.8_

- [ ] 4.2 Implement handleLeavePosition(market) method
  - Show confirmation modal
  - Display position details (size, entry, mark, PnL)
  - Calculate expected proceeds
  - _Requirements: 4.8_

- [ ] 4.3 Implement confirmLeavePosition() method
  - Send DRIFT_CLOSE_POSITION command
  - Include market name
  - Show loading state
  - Disable all action buttons
  - _Requirements: 4.9, 8.7_

- [ ] 4.4 Handle position close response
  - Show success toast with PnL
  - Show error toast if failed
  - Update positions table
  - Re-enable action buttons
  - _Requirements: 4.12, 8.8, 8.9_

- [ ] 4.5 Add "Settle PnL" button
  - Show button if unsettled PnL > $1.00
  - Send settle command on click
  - Update PnL display after settlement
  - _Requirements: 4.10, 4.11_

- [ ] 4.6 Write property test for position close sizing
  - **Property 15: Position Close Sizing**
  - **Validates: Requirements 4.8**
  - For any position with size S, close command should generate offsetting order of size S

- [ ] 4.7 Write property test for conditional PnL settlement
  - **Property 16: Conditional PnL Settlement**
  - **Validates: Requirements 4.10**
  - For any position close, if unsettled PnL > $1.00, settle_pnl should be called

- [ ] 5. WebSocket Integration
  - Add FUNDING_UPDATE handler
  - Add COMMAND_RESULT handler
  - Add HEALTH_ALERT handler
  - Update UI components in real-time
  - _Requirements: 1.7, 2.9, 4.12, 8.10_

- [ ] 5.1 Implement handleFundingUpdate(data) method
  - Parse FUNDING_UPDATE message
  - Update health gauge (rotate needle)
  - Update leverage meter (fill bar)
  - Update delta display (value and status)
  - Update positions table
  - Update collateral metrics
  - _Requirements: 1.7, 2.9, 4.12_

- [ ] 5.2 Update health gauge animation
  - Calculate needle rotation angle from health ratio
  - Animate needle rotation (smooth transition)
  - Update health percentage text
  - Update health label (HEALTHY/WARNING/CRITICAL)
  - Change colors based on thresholds
  - _Requirements: 2.4, 2.5_

- [ ] 5.3 Update leverage meter
  - Calculate fill percentage from leverage
  - Animate bar fill (smooth transition)
  - Update leverage text (e.g., "2.5x")
  - Change color based on leverage (green < 3x, yellow < 5x, red ≥ 5x)
  - _Requirements: 4.2, 6.7_

- [ ] 5.4 Update delta display
  - Update net delta value
  - Update delta status (NEUTRAL/LONG BIAS/SHORT BIAS)
  - Change color based on drift percentage
  - _Requirements: 5.1, 5.2_

- [ ] 5.5 Update positions table
  - Clear existing rows
  - Render new position rows
  - Update PnL colors (green positive, red negative)
  - Update liquidation price
  - _Requirements: 4.12_

- [ ] 5.6 Implement handleHealthAlert(data) method
  - Show warning banner for health < 50%
  - Show critical alert for health < 20%
  - Include health percentage and message
  - Add dismiss button
  - Auto-dismiss after 10 seconds
  - _Requirements: 2.4, 2.5_

- [ ] 5.7 Write property test for broadcast latency
  - **Property 8: Broadcast Latency**
  - **Validates: Requirements 2.9**
  - For any state change, WebSocket broadcast should occur within 500ms

- [ ] 5.8 Write property test for message completeness
  - **Property 5: WebSocket Message Completeness**
  - **Validates: Requirements 1.7, 8.10**
  - For any FUNDING_UPDATE, message should contain all required fields

- [ ] 6. Testing & Polish
  - Write unit tests
  - Write property tests
  - Write integration tests
  - UI polish and error handling
  - _Requirements: All_

- [ ] 6.1 Write unit tests for delta drift calculation
  - Test with various spot/perp combinations
  - Test with zero values
  - Test with negative perp (short position)
  - _Requirements: 5.1_

- [ ] 6.2 Write property test for delta drift calculation
  - **Property 18: Delta Drift Calculation**
  - **Validates: Requirements 5.1**
  - For any spot S, perp P, reserved R, drift should equal ((S - R + P) / (S - R)) × 100

- [ ] 6.3 Write unit tests for health ratio calculation
  - Test with various collateral/margin combinations
  - Test edge cases (zero margin, zero collateral)
  - Test clamping to [0, 100] range
  - _Requirements: 1.4, 2.3_

- [ ] 6.4 Write property test for health ratio calculation
  - **Property 2: Health Ratio Calculation**
  - **Validates: Requirements 1.4, 2.3**
  - For any collateral C and margin M, health should equal (C / M) × 100, clamped to [0, 100]

- [ ] 6.5 Write unit tests for profitability checks
  - Test with various funding rates and costs
  - Test conservative estimate (50% haircut)
  - Test rejection when unprofitable
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 6.6 Write property test for profitability check
  - **Property 27: Profitability Check**
  - **Validates: Requirements 6.3**
  - For any expected revenue E and cost C, trade should be rejected if E < C

- [ ] 6.7 Write property test for conservative funding estimate
  - **Property 28: Conservative Funding Estimate**
  - **Validates: Requirements 6.4**
  - For any funding rate R, profitability calculation should use 0.5 × R

- [ ] 6.8 Write integration test for full position lifecycle
  - Start engine in paper mode
  - Fetch market opportunities
  - Take position (open)
  - Verify position appears in table
  - Leave position (close)
  - Verify position removed from table
  - Stop engine
  - _Requirements: 4.1, 4.7, 4.8, 4.12_

- [ ] 6.9 Write integration test for error handling
  - Test invalid market name
  - Test insufficient balance
  - Test leverage limit exceeded
  - Test network timeout
  - Verify error messages displayed
  - _Requirements: 4.1, 4.2, 6.7, 9.1, 9.2_

- [ ] 6.10 Write integration test for WebSocket reconnection
  - Disconnect WebSocket
  - Verify reconnection attempts
  - Verify state sync after reconnection
  - _Requirements: 9.5, 9.6_

- [ ] 6.11 Add loading skeletons
  - Add skeleton for funding table while loading
  - Add skeleton for opportunity cards
  - Add skeleton for positions table
  - _Requirements: 2.1_

- [ ] 6.12 Add error states
  - Show error message if API fails
  - Show retry button
  - Show error icon in table
  - _Requirements: 9.1, 9.2_

- [ ] 6.13 Add empty states
  - Show "No opportunities found" if markets empty
  - Show "No positions" if positions empty
  - Add helpful text and icons
  - _Requirements: 2.2_

- [ ] 6.14 Improve mobile responsiveness
  - Make tables scrollable on mobile
  - Stack opportunity cards vertically
  - Adjust font sizes for small screens
  - _Requirements: UI/UX_

- [ ] 6.15 Add keyboard shortcuts
  - R: Refresh market data
  - Escape: Close modals
  - Enter: Confirm actions
  - _Requirements: UI/UX_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Run all unit tests
  - Run all property tests (100 iterations each)
  - Run all integration tests
  - Fix any failing tests
  - Verify UI works in both paper and live modes

---

## Notes

- All tasks are required for comprehensive implementation
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties (100 iterations each)
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end flows
- Checkpoint ensures incremental validation

---

## Estimated Timeline

- **Phase 1** (Backend API): 3-4 hours
- **Phase 2** (Market Display): 4-5 hours
- **Phase 3** (Take Position): 3-4 hours
- **Phase 4** (Leave Position): 3-4 hours
- **Phase 5** (WebSocket): 2-3 hours
- **Phase 6** (Testing & Polish): 3-4 hours

**Total**: 18-24 hours (comprehensive with all tests)

---

## Success Criteria

✅ Market opportunities displayed with live funding rates  
✅ "Take Position" button opens position with user-specified size  
✅ "Leave Position" button closes position and shows PnL  
✅ Real-time updates via WebSocket (health, leverage, positions)  
✅ All safety gates enforced (leverage, health, profitability)  
✅ Error handling with user-friendly messages  
✅ Works in both paper mode and live mode  
✅ All critical property tests passing (100 iterations)

---

**Document Version**: 1.0  
**Created**: 2026-01-16  
**Status**: Ready for Execution
