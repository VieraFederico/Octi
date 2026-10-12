# Spec 01 — Final verification coverage

Spec: v1.0. Staged verification (D-118).
Verdict: NOT COMPLETE — live/browser checks not run; NFR-103 timing target not met.
Offline result: full suite green — 724 passed, 2 deselected in 60.29 s. VC-163 timing target not met (0.29 s over).

## Verification criteria and executable evidence

| VC | Test evidence | Status |
|---|---|---|
| VC-101 | <code>tests/functional/test_ingestion_flow.py::test_upload_pause_resume_and_history</code><br><code>tests/functional/test_ingestion_verification.py::test_question_follows_any_finished_upload_in_one_turn</code><br><code>tests/unit/test_chat.py::test_submission_parts_keep_pdf_bytes_in_memory</code> | PASSED — OFFLINE |
| VC-102 | <code>tests/functional/test_ingestion_flow.py::test_duplicate_and_replace_modals</code><br><code>tests/functional/test_ingestion_verification.py::test_identical_file_modal_never_starts_ingestion</code><br><code>tests/unit/test_upload.py::test_identical_file_precedes_replacement</code> | PASSED — OFFLINE |
| VC-103 | <code>tests/functional/test_ingestion_flow.py::test_duplicate_and_replace_modals</code><br><code>tests/functional/test_ingestion_verification.py::test_replacement_modal_reports_count_and_honors_choice</code><br><code>tests/unit/test_upload.py::test_same_name_needs_replacement_and_new_name_can_start</code> | PASSED — OFFLINE |
| VC-104 | <code>tests/functional/test_ingestion_flow.py::test_upload_pause_resume_and_history</code><br><code>tests/functional/test_ingestion_verification.py::test_question_follows_any_finished_upload_in_one_turn</code><br><code>tests/unit/test_chat.py::test_submission_parts_keep_pdf_bytes_in_memory</code> | PASSED — OFFLINE |
| VC-105 | <code>tests/unit/test_document.py::test_bytes_that_are_not_a_pdf_are_unreadable</code><br><code>tests/unit/test_ingestion_final_graph.py::test_rejected_documents_leave_every_store_unchanged</code><br><code>tests/unit/test_nodes.py::test_load_pdf_rejects_bytes_that_are_not_a_pdf</code> | PASSED — OFFLINE |
| VC-106 | <code>tests/unit/test_document.py::test_password_protected_pdf_is_refused</code><br><code>tests/unit/test_ingestion_final_graph.py::test_rejected_documents_leave_every_store_unchanged</code><br><code>tests/unit/test_nodes.py::test_load_pdf_rejects_a_password_protected_pdf</code> | PASSED — OFFLINE |
| VC-107 | <code>tests/unit/test_document.py::test_pdf_without_selectable_text_is_refused</code><br><code>tests/unit/test_ingestion_final_graph.py::test_rejected_documents_leave_every_store_unchanged</code><br><code>tests/unit/test_nodes.py::test_load_pdf_rejects_a_pdf_with_no_selectable_text</code> | PASSED — OFFLINE |
| VC-108 | <code>tests/unit/test_tables.py::test_two_tables_on_a_page_get_positions_from_the_top</code> | PASSED — OFFLINE |
| VC-109 | <code>tests/unit/test_tables.py::test_fake_tables_are_dropped_and_logged</code> | PASSED — OFFLINE |
| VC-110 | <code>tests/unit/test_tables.py::test_table_split_over_two_pages_is_one_table</code><br><code>tests/unit/test_tables.py::test_three_page_chain_is_one_table</code> | PASSED — OFFLINE |
| VC-111 | <code>tests/unit/test_tables.py::test_next_page_table_with_a_different_header_is_another_table</code><br><code>tests/unit/test_tables.py::test_next_page_table_with_another_column_count_is_another_table</code> | PASSED — OFFLINE |
| VC-112 | <code>tests/unit/test_cleaning.py::test_merged_header_levels_keep_their_measure_and_year</code><br><code>tests/unit/test_tables.py::test_two_row_merged_header_at_pdf_level</code> | PASSED — OFFLINE |
| VC-113 | <code>tests/unit/test_tables.py::test_bold_numeric_first_row_is_a_header_row</code><br><code>tests/unit/test_tables.py::test_plain_numeric_first_row_is_data</code> | PASSED — OFFLINE |
| VC-114 | <code>tests/unit/test_cleaning.py::test_uncovered_header_position_does_not_copy_the_left_label</code><br><code>tests/unit/test_pymupdf_assumptions.py::test_covered_position_is_none_and_empty_cell_is_an_empty_string</code><br><code>tests/unit/test_tables.py::test_empty_header_cell_next_to_total_at_pdf_level</code> | PASSED — OFFLINE |
| VC-115 | <code>tests/unit/test_cleaning.py::test_repeated_and_empty_headers_receive_unique_flat_names</code> | PASSED — OFFLINE |
| VC-116 | <code>tests/unit/test_tables.py::test_all_header_looking_table_keeps_one_data_row</code><br><code>tests/unit/test_tables.py::test_at_most_three_header_rows</code> | PASSED — OFFLINE |
| VC-117 | <code>tests/unit/test_cleaning.py::test_dataframe_builder_keeps_labels_and_cleans_each_measure_independently</code><br><code>tests/unit/test_cleaning.py::test_first_text_column_supplies_row_headers_without_being_removed</code> | PASSED — OFFLINE |
| VC-118 | <code>tests/unit/test_cleaning.py::test_every_specified_missing_marker_becomes_nan_in_a_numeric_column</code><br><code>tests/unit/test_cleaning.py::test_missing_values_make_an_otherwise_whole_column_float64</code><br><code>tests/unit/test_cleaning.py::test_whole_numbers_without_gaps_are_int64</code> | PASSED — OFFLINE |
| VC-119 | <code>tests/unit/test_cleaning.py::test_number_decorations_preserve_the_written_amount_and_symbol</code> | PASSED — OFFLINE |
| VC-120 | <code>tests/unit/test_cleaning.py::test_ambiguous_dot_defaults_to_english_decimal_style</code><br><code>tests/unit/test_cleaning.py::test_european_decimal_evidence_applies_to_every_cell_in_the_column</code> | PASSED — OFFLINE |
| VC-121 | <code>tests/unit/test_cleaning.py::test_one_unparseable_cell_keeps_the_entire_column_exactly_as_written</code> | PASSED — OFFLINE |
| VC-122 | <code>tests/unit/test_cleaning.py::test_dataframe_builder_keeps_labels_and_cleans_each_measure_independently</code><br><code>tests/unit/test_cleaning.py::test_hints_are_deduplicated_and_keep_their_written_symbols</code><br><code>tests/unit/test_prompts.py::test_columns_table_lists_exact_name_dtype_and_hint</code> | PASSED — OFFLINE |
| VC-123 | <code>tests/unit/test_document.py::test_pages_without_text_are_listed_1_based</code><br><code>tests/unit/test_graph.py::test_image_only_pages_pause_before_any_model_call</code><br><code>tests/unit/test_graph.py::test_unreadable_table_is_named_and_never_sent_to_the_model</code><br><code>tests/unit/test_tables.py::test_mostly_unreadable_table_is_flagged_and_not_cleaned</code> | PASSED — OFFLINE |
| VC-124 | <code>tests/unit/test_graph.py::test_cancel_at_the_unreadable_pause_leaves_the_previous_version</code><br><code>tests/unit/test_graph.py::test_continue_indexes_the_readable_tables</code> | PASSED — OFFLINE |
| VC-125 | <code>tests/unit/test_document.py::test_large_image_is_reported_and_a_repeated_small_logo_is_not</code> | PASSED — OFFLINE |
| VC-126 | <code>tests/unit/test_context.py::test_caption_below_the_table_is_found</code><br><code>tests/unit/test_context.py::test_each_field_is_found</code><br><code>tests/unit/test_context.py::test_no_caption_at_all</code><br><code>tests/unit/test_context.py::test_short_block_above_is_the_caption_fallback</code> | PASSED — OFFLINE |
| VC-127 | <code>tests/unit/test_context.py::test_other_column_running_header_and_page_number_never_count</code> | PASSED — OFFLINE |
| VC-128 | <code>tests/unit/test_context.py::test_multi_page_table_takes_caption_from_first_part_and_footnote_from_last</code> | PASSED — OFFLINE |
| VC-129 | <code>tests/unit/test_context.py::test_context_is_cut_to_the_limits</code> | PASSED — OFFLINE |
| VC-130 | <code>tests/unit/test_nodes.py::test_enrich_calls_the_configured_model_with_structured_output</code> | PASSED — OFFLINE |
| VC-131 | <code>tests/unit/test_prompts.py::test_messages_are_system_two_example_pairs_then_the_human_message</code><br><code>tests/unit/test_prompts.py::test_system_message_is_identical_for_two_tables</code><br><code>tests/unit/test_prompts.py::test_system_message_is_prompt_v1_of_the_spec</code> | PASSED — OFFLINE |
| VC-132 | <code>tests/unit/test_prompts.py::test_backtick_fences_in_pdf_text_cannot_close_a_fence</code><br><code>tests/unit/test_prompts.py::test_human_message_sections_are_in_fr_130_order</code> | PASSED — OFFLINE |
| VC-133 | <code>tests/unit/test_validation.py::test_description_over_600_characters_is_a_shape_problem</code><br><code>tests/unit/test_validation.py::test_empty_name_description_and_column_description</code><br><code>tests/unit/test_validation.py::test_generic_names_are_rejected</code><br><code>tests/unit/test_validation.py::test_missing_unknown_and_repeated_columns_each_get_their_own_sentence</code><br><code>tests/unit/test_validation.py::test_percent_column_needs_a_percent_unit</code> | PASSED — OFFLINE |
| VC-134 | <code>tests/unit/test_graph.py::test_a_table_is_indexed_on_the_third_attempt</code><br><code>tests/unit/test_graph.py::test_three_invalid_answers_pause_as_skipped</code><br><code>tests/unit/test_prompts.py::test_retry_adds_previous_answer_and_feedback_before_the_task</code> | PASSED — OFFLINE |
| VC-135 | <code>tests/unit/test_graph.py::test_zero_retries_skips_a_table_after_one_attempt</code> | PASSED — OFFLINE |
| VC-136 | <code>tests/unit/test_graph.py::test_the_next_table_does_not_inherit_feedback</code> | PASSED — OFFLINE |
| VC-137 | <code>tests/unit/test_graph.py::test_cancel_at_the_skipped_pause_writes_nothing</code><br><code>tests/unit/test_graph.py::test_every_table_skipped_offers_only_cancel</code><br><code>tests/unit/test_graph.py::test_one_skipped_table_can_be_indexed</code> | PASSED — OFFLINE |
| VC-138 | <code>tests/unit/test_indexing.py::test_facts_come_from_extraction_whatever_the_llm_wrote</code> | PASSED — OFFLINE |
| VC-139 | <code>tests/unit/test_indexing.py::test_embedding_text_cuts_row_headers_at_fifty_with_the_rest_counted</code><br><code>tests/unit/test_indexing.py::test_embedding_text_has_name_description_columns_and_row_headers</code> | PASSED — OFFLINE |
| VC-140 | <code>tests/unit/test_indexing.py::test_each_record_has_its_parquet_file_with_the_same_dtypes</code><br><code>tests/unit/test_indexing.py::test_the_write_order_is_embed_then_files_then_upserts_then_deletes</code><br><code>tests/unit/test_table_store.py::test_a_table_written_is_read_back_equal_with_its_dtypes</code><br><code>tests/unit/test_vector_store.py::test_upsert_sends_batches_of_100</code> | PASSED — OFFLINE |
| VC-141 | <code>tests/unit/test_indexing.py::test_a_new_version_replaces_the_old_one</code> | PASSED — OFFLINE |
| VC-142 | <code>tests/unit/test_indexing.py::test_an_embedding_failure_writes_nothing_and_keeps_the_old_version</code><br><code>tests/unit/test_indexing.py::test_an_upsert_failure_removes_the_new_files_and_keeps_the_old_version</code> | PASSED — OFFLINE |
| VC-143 | <code>tests/unit/test_indexing.py::test_a_failure_deleting_the_old_version_keeps_the_new_one_and_says_so</code> | PASSED — OFFLINE |
| VC-144 | <code>tests/unit/test_indexing.py::test_four_hundred_long_column_descriptions_exceed_the_guard</code><br><code>tests/unit/test_ingestion_final_graph.py::test_oversized_table_is_offered_at_pause_and_only_others_are_indexed</code><br><code>tests/unit/test_nodes.py::test_validate_skips_metadata_over_the_size_guard</code> | PASSED — OFFLINE |
| VC-145 | <code>tests/unit/test_graph.py::test_continuing_past_an_unreadable_only_pdf_indexes_nothing</code><br><code>tests/unit/test_graph.py::test_text_without_tables_keeps_the_previous_version</code> | PASSED — OFFLINE |
| VC-146 | <code>tests/unit/test_graph_routing.py::test_six_tables_that_fail_every_attempt_finish_within_the_recursion_limit</code> | PASSED — OFFLINE |
| VC-147 | <code>tests/unit/test_graph.py::test_the_same_bytes_twice_keep_the_same_record_ids</code><br><code>tests/unit/test_indexing.py::test_the_same_document_twice_leaves_the_same_ids_and_count</code> | PASSED — OFFLINE |
| VC-148 | <code>tests/functional/test_ingestion_flow.py::test_upload_pause_resume_and_history</code><br><code>tests/functional/test_ingestion_verification.py::test_both_pauses_resume_inside_the_run_message</code><br><code>tests/unit/test_ingestion_ui.py::test_run_status_reports_describing_attempt</code> | PASSED — OFFLINE |
| VC-149 | <code>tests/functional/test_ingestion_verification.py::test_finished_summary_contains_all_cards_notes_and_survives_navigation</code><br><code>tests/unit/test_table_card.py::test_card_has_fields_escaped_text_and_scrolling_preview</code> | PASSED — OFFLINE |
| VC-150 | <code>tests/functional/test_ingestion_flow.py::test_upload_pause_resume_and_history</code><br><code>tests/functional/test_ingestion_verification.py::test_finished_summary_contains_all_cards_notes_and_survives_navigation</code> | PASSED — OFFLINE |
| VC-151 | Removed with FR-148 (D-095) | REMOVED |
| VC-152 | <code>tests/functional/test_ingestion_verification.py::test_catalog_order_filter_and_document_navigation</code><br><code>tests/functional/test_ingestion_verification.py::test_session_reads_fake_index_once_and_adds_run_results_without_reload</code><br><code>tests/unit/test_catalog_ui.py::test_catalog_load_and_run_update</code> | PASSED — OFFLINE |
| VC-153 | <code>tests/functional/test_ingestion_verification.py::test_catalog_order_filter_and_document_navigation</code><br><code>tests/functional/test_library.py::test_library_groups_cards_and_filters_documents</code> | PASSED — OFFLINE |
| VC-154 | <code>tests/functional/test_ingestion_verification.py::test_catalog_order_filter_and_document_navigation</code><br><code>tests/functional/test_library.py::test_library_groups_cards_and_filters_documents</code> | PASSED — OFFLINE |
| VC-155 | <code>tests/functional/test_ingestion_verification.py::test_catalog_order_filter_and_document_navigation</code><br><code>tests/unit/test_documents.py::test_document_navigation_preserves_local_expanders</code> | PASSED — OFFLINE |
| VC-156 | <code>tests/unit/test_tracing_config.py::test_a_resumed_run_keeps_the_same_thread_id</code><br><code>tests/unit/test_tracing_config.py::test_run_config_labels_one_ingestion</code> | PASSED — OFFLINE |
| VC-157 | <code>tests/unit/test_tracing_config.py::test_tracing_on_uses_the_settings_project_without_env_variables</code> | PASSED — OFFLINE |
| VC-158 | <code>tests/unit/test_settings.py::test_env_example_documents_ingestion_max_retries</code><br><code>tests/unit/test_settings.py::test_ingestion_max_retries_defaults_to_2_and_accepts_up_to_5</code><br><code>tests/unit/test_settings.py::test_ingestion_max_retries_outside_0_to_5_is_rejected</code> | PASSED — OFFLINE |
| VC-159 | <code>tests/unit/test_graph.py::test_fake_secrets_stay_out_of_prompts_and_state</code><br><code>tests/unit/test_tracing_config.py::test_run_config_contains_no_secret</code> | PASSED — OFFLINE |
| VC-160 | <code>tests/unit/test_nodes.py::test_skipped_table_feedback_is_logged_and_kept_out_of_the_part</code> | PASSED — OFFLINE |
| VC-161 | <code>tests/unit/test_sample_pdfs.py::test_acme_has_every_table_on_its_pages</code><br><code>tests/unit/test_sample_pdfs.py::test_acme_headcount_table_on_the_two_column_page</code><br><code>tests/unit/test_sample_pdfs.py::test_acme_income_table_has_gross_and_net_revenue</code><br><code>tests/unit/test_sample_pdfs.py::test_acme_monthly_table_spans_two_pages_and_sums_to_the_year</code><br><code>tests/unit/test_sample_pdfs.py::test_acme_rd_table</code><br><code>tests/unit/test_sample_pdfs.py::test_acme_regional_table_has_merged_header_and_no_national_row</code><br><code>tests/unit/test_sample_pdfs.py::test_informe_tables_use_european_decimals</code><br><code>tests/unit/test_sample_pdfs.py::test_running_the_script_twice_gives_the_same_tables</code> | PASSED — OFFLINE |
| VC-162 | <code>tests/unit/test_ingestion_final_graph.py::test_exported_graph_includes_the_actual_conditional_routes</code><br><code>tests/unit/test_readme.py::test_ingestion_documentation_and_exported_graph_are_present</code><br><code>tests/unit/test_readme.py::test_ingestion_status_and_usage_describe_the_shipped_ui</code> | PASSED — OFFLINE |
| VC-163 | wsl .venv/bin/python -m pytest -q (network and secret-file guards enabled) | PARTIAL — suite green; 60.29 s exceeds 60 s |
| VC-164 | <code>tests/live/test_ingestion_live.py::test_acme_ingestion_has_expected_tables_and_files</code> | NOT RUN — LIVE |
| VC-165 | <code>tests/unit/test_prompts.py::test_message_list_for_a_big_table_stays_within_the_prompt_budget</code> | PASSED — OFFLINE |
| VC-166 | Student: ACME under 3 minutes, status updates within 2 seconds, browser layout at both widths | NOT RUN — MANUAL |
| VC-167 | <code>tests/unit/test_ingestion_final_graph.py::test_checkpoints_and_updates_keep_only_twenty_rows</code><br><code>tests/unit/test_nodes.py::test_a_two_hundred_row_table_stays_out_of_the_node_output</code><br><code>tests/unit/test_state.py::test_a_run_holds_its_bytes_until_it_is_closed</code><br><code>tests/unit/test_state.py::test_closing_a_run_closes_its_document_and_is_idempotent</code> | PASSED — OFFLINE |
| VC-168 | <code>tests/unit/test_ingestion_final_graph.py::test_second_table_model_outage_ends_without_a_pause_or_any_write</code><br><code>tests/unit/test_nodes.py::test_enrich_ends_the_run_when_the_model_call_fails</code> | PASSED — OFFLINE |
| VC-169 | <code>tests/unit/test_context.py::test_header_line_repeated_on_four_pages_is_not_section</code><br><code>tests/unit/test_context.py::test_one_page_pdf_keeps_its_context</code><br><code>tests/unit/test_document.py::test_large_image_repeated_on_every_page_is_not_reported</code><br><code>tests/unit/test_document.py::test_one_page_pdf_reports_its_large_image</code> | PASSED — OFFLINE |
| VC-170 | <code>tests/functional/test_ingestion_flow.py::test_upload_pause_resume_and_history</code><br><code>tests/functional/test_ingestion_verification.py::test_both_pauses_resume_inside_the_run_message</code> | PASSED — OFFLINE |
| VC-171 | <code>tests/functional/test_ingestion_verification.py::test_new_chat_at_a_pause_empties_the_run_without_writes</code><br><code>tests/unit/test_ingestion_ui.py::test_erasing_a_paused_run_releases_its_data</code> | PASSED — OFFLINE |
| VC-172 | <code>tests/functional/test_ingestion_verification.py::test_catalog_outage_refuses_upload_and_recovery_retries_before_run</code><br><code>tests/unit/test_catalog_ui.py::test_failed_catalog_load_can_be_retried</code><br><code>tests/unit/test_indexing.py::test_load_catalog_failure_is_a_vector_store_error</code><br><code>tests/unit/test_vector_store.py::test_pinecone_failures_become_vector_store_errors</code> | PASSED — OFFLINE |
| VC-173 | <code>tests/functional/test_ingestion_verification.py::test_catalog_outage_refuses_upload_and_recovery_retries_before_run</code><br><code>tests/unit/test_catalog_ui.py::test_failed_catalog_load_can_be_retried</code> | PASSED — OFFLINE |
| VC-174 | <code>tests/unit/test_indexing.py::test_old_versions_found_only_in_pinecone_are_deleted</code> | PASSED — OFFLINE |

## Every requirement and its verification criteria

| Requirement | VCs (tests listed above) | Status |
|---|---|---|
| FR-101 | VC-101 | PASSED — OFFLINE |
| FR-102 | VC-102 | PASSED — OFFLINE |
| FR-103 | VC-103 | PASSED — OFFLINE |
| FR-104 | VC-104 | PASSED — OFFLINE |
| FR-105 | VC-105 | PASSED — OFFLINE |
| FR-106 | VC-106 | PASSED — OFFLINE |
| FR-107 | VC-107 | PASSED — OFFLINE |
| FR-108 | VC-105, VC-106, VC-107 | PASSED — OFFLINE |
| FR-109 | VC-108 | PASSED — OFFLINE |
| FR-110 | VC-109 | PASSED — OFFLINE |
| FR-111 | VC-110, VC-111 | PASSED — OFFLINE |
| FR-112 | VC-110 | PASSED — OFFLINE |
| FR-113 | VC-112, VC-113, VC-114, VC-115, VC-116 | PASSED — OFFLINE |
| FR-114 | VC-117 | PASSED — OFFLINE |
| FR-115 | VC-118 | PASSED — OFFLINE |
| FR-116 | VC-119, VC-120 | PASSED — OFFLINE |
| FR-117 | VC-118, VC-121 | PASSED — OFFLINE |
| FR-118 | VC-122 | PASSED — OFFLINE |
| FR-119 | VC-123 | PASSED — OFFLINE |
| FR-120 | VC-124 | PASSED — OFFLINE |
| FR-121 | VC-125, VC-169 | PASSED — OFFLINE |
| FR-122 | VC-123 | PASSED — OFFLINE |
| FR-123 | VC-126 | PASSED — OFFLINE |
| FR-124 | VC-127, VC-169 | PASSED — OFFLINE |
| FR-125 | VC-128 | PASSED — OFFLINE |
| FR-126 | VC-129 | PASSED — OFFLINE |
| FR-127 | VC-130 | PASSED — OFFLINE |
| FR-128 | VC-131 | PASSED — OFFLINE |
| FR-129 | VC-131 | PASSED — OFFLINE |
| FR-130 | VC-132 | PASSED — OFFLINE |
| FR-160 | VC-168 | PASSED — OFFLINE |
| FR-131 | VC-133 | PASSED — OFFLINE |
| FR-132 | VC-134, VC-135 | PASSED — OFFLINE |
| FR-133 | VC-136 | PASSED — OFFLINE |
| FR-134 | VC-137 | PASSED — OFFLINE |
| FR-135 | VC-137 | PASSED — OFFLINE |
| FR-136 | VC-138, VC-144 | PASSED — OFFLINE |
| FR-137 | VC-139 | PASSED — OFFLINE |
| FR-138 | VC-140, VC-141, VC-174 | PASSED — OFFLINE |
| FR-139 | VC-142 | PASSED — OFFLINE |
| FR-140 | VC-143 | PASSED — OFFLINE |
| FR-141 | VC-144 | PASSED — OFFLINE |
| FR-142 | VC-145 | PASSED — OFFLINE |
| FR-143 | VC-146 | PASSED — OFFLINE |
| FR-144 | VC-148 | PASSED — OFFLINE |
| FR-145 | VC-148 | PASSED — OFFLINE |
| FR-146 | VC-149 | PASSED — OFFLINE |
| FR-147 | VC-150 | PASSED — OFFLINE |
| FR-149 | VC-152 | PASSED — OFFLINE |
| FR-150 | VC-153 | PASSED — OFFLINE |
| FR-151 | VC-154 | PASSED — OFFLINE |
| FR-152 | VC-155 | PASSED — OFFLINE |
| FR-161 | VC-170 | PASSED — OFFLINE |
| FR-162 | VC-171 | PASSED — OFFLINE |
| FR-163 | VC-172 | PASSED — OFFLINE |
| FR-164 | VC-173 | PASSED — OFFLINE |
| FR-153 | VC-156 | PASSED — OFFLINE |
| FR-154 | VC-157 | PASSED — OFFLINE |
| FR-155 | VC-158 | PASSED — OFFLINE |
| FR-156 | VC-161 | PASSED — OFFLINE |
| FR-157 | VC-162 | PASSED — OFFLINE |
| FR-158 | VC-163 | PASSED — OFFLINE |
| FR-159 | VC-164 | NOT RUN — LIVE/MANUAL |
| BR-101 | VC-138 | PASSED — OFFLINE |
| BR-102 | VC-132 | PASSED — OFFLINE |
| BR-103 | VC-124, VC-137 | PASSED — OFFLINE |
| BR-104 | VC-147 | PASSED — OFFLINE |
| BR-105 | VC-142 | PASSED — OFFLINE |
| BR-106 | VC-160, VC-168, VC-172, VC-173 | PASSED — OFFLINE |
| BR-107 | VC-159 | PASSED — OFFLINE |
| BR-108 | VC-140 | PASSED — OFFLINE |
| BR-109 | VC-149 | PASSED — OFFLINE |
| BR-110 | VC-141, VC-174 | PASSED — OFFLINE |
| BR-111 | VC-167 | PASSED — OFFLINE |
| NFR-101 | VC-166 | NOT RUN — LIVE/MANUAL |
| NFR-102 | VC-166 | NOT RUN — LIVE/MANUAL |
| NFR-103 | VC-163 | NOT MET — 60.29 s |
| NFR-104 | VC-165 | PASSED — OFFLINE |
| NFR-105 | VC-144 | PASSED — OFFLINE |
| NFR-106 | VC-147 | PASSED — OFFLINE |
| NFR-107 | VC-166 | NOT RUN — LIVE/MANUAL |
| NFR-108 | VC-163 | PASSED — OFFLINE |

## Remaining student checks

- Run the marked live test; its storage is isolated (S01-D-025).
- Attach both sample PDFs in the real app, answer any pauses, check cards and Library/Document navigation.
- Check duplicate Keep/Open and replacement Cancel/Replace with the real composer.
- Check browser-owned View all/Show more and Document clicks; AppTest cannot execute the component JavaScript.
- Record ACME elapsed time and update latency; check 1280×800 and 375 px for page overflow.
- Confirm the full offline suite finishes under 60 seconds; this run took 60.29 seconds.
- Run sample regeneration and the documented app command.

## Verification boundaries

- VC-101 uses the pure attachment reader plus pending-upload AppTest injection; AppTest cannot attach PDFs.
- VC-155 covers escaped markup, catalog order and the Python navigation seam; the component click is a student browser check.
- VC-165 measures the specified representative 20-column/20-row fixture; unusually large cells remain the documented S01-D-016 limitation.
- No live check is waived or marked passed; no real service, secret file, install or Git mutation was used.
