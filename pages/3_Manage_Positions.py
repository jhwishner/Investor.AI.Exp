"""Log hypothetical BUY/SELL transactions and manage the paper portfolio ledger."""

from datetime import date

import streamlit as st

from investor_ai import config, data, fidelity_import, portfolio

user_id = st.session_state["user_id"]
st.title("Manage Positions")

st.caption(
    "Log a hypothetical trade here to track it in your paper portfolio. Nothing here places a "
    "real trade or connects to a brokerage -- it's purely for your own tracking and practice."
)

portfolio.init_db()

existing_accounts = portfolio.list_accounts(user_id)
existing_risk_levels = portfolio.list_risk_levels(user_id)

with st.form("add_transaction_form", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        ticker_input = st.text_input("Ticker", placeholder="e.g. AAPL").strip().upper()
        action = st.selectbox("Action", options=["BUY", "SELL"])
    with col2:
        quantity = st.number_input("Quantity (shares)", min_value=0.0, step=0.0001, format="%.6f")
        price = st.number_input("Price per share ($)", min_value=0.0, step=0.01, format="%.2f")
    with col3:
        trade_date = st.date_input("Trade date", value=date.today(), max_value=date.today())
        account_choice = st.selectbox("Account", options=existing_accounts)

    col4, col5 = st.columns(2)
    with col4:
        new_account_input = st.text_input(
            "Or create a new account (optional)",
            placeholder="e.g. Roth IRA, 401k, Robinhood",
            help="Leave blank to use the account selected above.",
        ).strip()
    with col5:
        risk_level_choice = st.selectbox(
            "Risk tag",
            options=existing_risk_levels,
            help="Independent of account -- lets you group positions by intent (e.g. steady core "
            "holdings vs. speculative bets) regardless of which account they're logged under.",
        )
        new_risk_level_input = st.text_input(
            "Or create a new risk tag (optional)",
            placeholder="e.g. Core, Moonshot",
            help="Leave blank to use the risk tag selected above.",
        ).strip()

    submitted = st.form_submit_button("Add transaction")

    if submitted:
        account = new_account_input or account_choice
        risk_level = new_risk_level_input or risk_level_choice
        if not ticker_input:
            st.error("Enter a ticker symbol.")
        elif quantity <= 0:
            st.error("Quantity must be greater than zero.")
        elif price <= 0:
            st.error("Price must be greater than zero.")
        else:
            is_valid, validation_message = data.validate_ticker(ticker_input)
            if not is_valid:
                st.error(validation_message)
            else:
                try:
                    portfolio.add_transaction(
                        ticker=ticker_input,
                        action=action,
                        quantity=quantity,
                        price=price,
                        trade_date=trade_date,
                        user_id=user_id,
                        account=account,
                        risk_level=risk_level,
                    )
                    st.success(f"Logged {action} {quantity} {ticker_input} @ ${price:.2f} in '{account}' ({risk_level})")
                except portfolio.InsufficientHoldingsError as e:
                    st.error(str(e))
                except ValueError as e:
                    st.error(str(e))

st.divider()
st.subheader("Import from Fidelity")
st.caption(
    "Fidelity doesn't offer a way for personal apps to connect directly to your account, so the "
    "practical option is exporting your transaction history and uploading it here."
)

with st.expander("How to export from Fidelity", icon=":material/help:"):
    st.markdown(
        "1. Log in at [fidelity.com](https://www.fidelity.com) and go to **Accounts & Trade > "
        "Activity & Orders**.\n"
        "2. Pick the account and date range, then click **Export**.\n"
        "3. Upload the downloaded CSV below.\n\n"
        "Only actual buy/sell trades are imported -- dividends, interest, and transfers are "
        "skipped. Rows already in your ledger (same ticker, action, quantity, price, date, and "
        "account) are skipped automatically, so re-uploading an overlapping export is safe."
    )

uploaded_file = st.file_uploader("Fidelity transaction history CSV", type="csv")
if uploaded_file is not None:
    try:
        parsed_trades = fidelity_import.parse_fidelity_csv(uploaded_file)
    except ValueError as e:
        st.error(str(e))
    else:
        if parsed_trades.empty:
            st.warning("No buy/sell trades found in this file.")
        else:
            st.caption(f"Found {len(parsed_trades)} trade row(s) in this file.")
            preview_df = fidelity_import.prepare_preview_dataframe(parsed_trades)
            st.caption("Review and edit any row before importing. This is the place to fix mismatched account names.")
            edited_preview = st.data_editor(
                preview_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "trade_date": st.column_config.DateColumn("Trade date", format="YYYY-MM-DD"),
                    "account": st.column_config.TextColumn("Account"),
                    "ticker": st.column_config.TextColumn("Ticker"),
                    "action": st.column_config.SelectboxColumn(
                        "Action",
                        options=["BUY", "SELL"],
                        required=True,
                    ),
                    "quantity": st.column_config.NumberColumn("Quantity", step=0.0001, min_value=0.0, format="%.6f"),
                    "price": st.column_config.NumberColumn("Price", format="%.2f", min_value=0.0),
                },
            )

            if st.button("Import edited preview", icon=":material/upload:"):
                try:
                    finalized_rows = fidelity_import.prepare_preview_dataframe(edited_preview)
                except ValueError as e:
                    st.error(str(e))
                else:
                    import_result = fidelity_import.import_transactions(finalized_rows, user_id)
                    if import_result.imported:
                        st.success(f"Imported {import_result.imported} new transaction(s).")
                    if import_result.duplicates:
                        st.caption(f"Skipped {import_result.duplicates} row(s) already in your ledger.")
                    if import_result.failed:
                        st.warning(f"Couldn't import {len(import_result.failed)} row(s):")
                        for failure_message in import_result.failed:
                            st.caption(f"- {failure_message}")
                    if import_result.imported:
                        st.rerun()

@st.dialog("Delete transactions?")
def _confirm_bulk_delete(transaction_ids: list[int]) -> None:
    st.write(
        f"This will permanently delete **{len(transaction_ids)}** transaction(s) from your ledger. "
        "This can't be undone."
    )
    if st.button(f"Delete {len(transaction_ids)}", icon=":material/delete_forever:", type="primary"):
        deleted = portfolio.delete_transactions(transaction_ids, user_id)
        st.toast(f"Deleted {deleted} transaction(s).", icon=":material/check_circle:")
        st.rerun()


st.divider()
st.subheader("Transaction history")

all_transactions = portfolio.list_transactions(user_id)
if all_transactions.empty:
    st.info("No transactions logged yet.")
else:
    _DISPLAY_COLS = ["id", "trade_date", "account", "risk_level", "ticker", "action", "quantity", "price", "notes"]
    st.caption("Select rows to delete them -- click a row, shift-click for a range, or use the header checkbox.")
    selection_event = st.dataframe(
        all_transactions[_DISPLAY_COLS],
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key="transactions_table",
    )

    selected_positions = selection_event.selection.rows
    if selected_positions:
        selected_ids = all_transactions.iloc[selected_positions]["id"].tolist()
        if st.button(
            f"Delete {len(selected_ids)} selected transaction(s)", icon=":material/delete:", type="secondary"
        ):
            _confirm_bulk_delete(selected_ids)

st.divider()
st.caption(config.DISCLAIMER)
