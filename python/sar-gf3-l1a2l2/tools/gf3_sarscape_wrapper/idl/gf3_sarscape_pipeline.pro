function gf3_normalize_errmsg, value
  compile_opt idl2

  if n_elements(value) eq 0 then return, ''

  sz = size(value, /tname)

  if sz eq 'STRING' then begin
    if n_elements(value) eq 1 then return, value
    return, strjoin(value, ' ')
  endif

  if sz eq 'BYTE' then begin
    if n_elements(value) eq 0 then return, ''
    return, string(value)
  endif

  return, string(value)
end


function gf3_float_str, value
  compile_opt idl2
  return, string(double(value), format='(F0.1)')
end


function gf3_base_root, polarization
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  pol = strupcase(strtrim(polarization, 2))
  case pol of
    'HH': return, cfg.imported_hh_root
    'HV': return, cfg.imported_hv_root
    else: message, 'Unsupported polarization: ' + pol
  endcase
end


function gf3_stage_root, polarization, stage_name
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  pol = strlowcase(strtrim(polarization, 2))
  prefix = cfg.output_prefix
  if prefix eq '' then prefix = 'gf3'

  case strlowcase(strtrim(stage_name, 2)) of
    'multilook': return, cfg.out_dir + '\' + prefix + '_' + pol + '_ml'
    'filter': return, cfg.out_dir + '\' + prefix + '_' + pol + '_filt'
    'geocode': return, cfg.out_dir + '\' + prefix + '_' + pol + '_geo'
    else: message, 'Unsupported stage: ' + stage_name
  endcase
end


function gf3_scene_token, meta_xml
  compile_opt idl2

  base = file_basename(meta_xml)
  pos = strpos(strlowcase(base), '.meta.xml')
  if pos ge 0 then base = strmid(base, 0, pos)
  return, base
end


function gf3_imported_root_for, polarization
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  pol = strupcase(strtrim(polarization, 2))
  pattern = cfg.out_dir + '\*_' + pol + '_slc.sml'
  matches = file_search(pattern, count=count)
  if count eq 0 then return, ''

  newest = matches[0]
  newest_time = (file_info(newest)).mtime
  for i = 1, count - 1 do begin
    info = file_info(matches[i])
    if info.mtime gt newest_time then begin
      newest = matches[i]
      newest_time = info.mtime
    endif
  endfor

  return, strmid(newest, 0, strlen(newest) - 4)
end


pro gf3_refresh_import_roots
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  hh = gf3_imported_root_for('HH')
  hv = gf3_imported_root_for('HV')

  if hh ne '' then cfg.imported_hh_root = hh
  if hv ne '' then cfg.imported_hv_root = hv
end


pro gf3_run_module, module_name, set_params_proc, errmsg=errmsg, working_directory=working_directory
  compile_opt idl2

  errmsg = ''
  ob = obj_new('SARscapeBatch', Module=module_name)
  if ~obj_valid(ob) then begin
    errmsg = 'Create object failed: ' + module_name
    print, errmsg
    return
  endif

  ob->SetParam, 'GENERAL_PARAMETERS_CMD.AVAILABLE_MEMORY_SIZE_GB', '8.0000000'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.LOAD_IMAGES', 'OK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.DELETE_TEMPORARY_FILES', 'OK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.MAKE_TIFF', 'OK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.QUICK_LOOK_FORMAT', 'ql_tiff'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.SARSCAPE_TRACE_LEVEL', '3.0000000'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.RENAME_THE_FILE_USING_PARAMETERS_FLAG', 'OK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.INSERT_GEO_POINTS_FLAG', 'NotOK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.VERBOSE_TRACE', 'OK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.VERBOSE_STEP', 'OK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.VERBOSE_BAR', 'OK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.APPLY_CALIBRATION_CONSTANT_FLAG', 'OK'
  ob->SetParam, 'GENERAL_PARAMETERS_CMD.FILL_DUMMY_DURING_IMPORT', 'OK'

  call_procedure, set_params_proc, ob

  ok = ob->VerifyParams(Silent=0)
  if ~ok then begin
    errmsg = 'VerifyParams failed: ' + module_name
    print, errmsg
    return
  endif

  if n_elements(working_directory) eq 0 then begin
    ok = ob->Execute()
  endif else begin
    exec_errmsg = ''
    ok = ob->Execute(WORKING_DIRECTORY=working_directory, ERRMSG=exec_errmsg)
    errmsg = gf3_normalize_errmsg(exec_errmsg)
  endelse

  if ok then begin
    print, 'Success: ' + module_name
  endif else begin
    if errmsg eq '' then begin
      err_code = ''
      err_text = get_SARscape_error_string('OK', ERROR_CODE=err_code)
      errmsg = 'Execution failed [' + module_name + '] EC [' + err_code + ']: ' + err_text
    endif
    print, errmsg
  endelse
end


pro gf3_pipeline_set_import_params, ob
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  ob->SetParam, 'MAIN_BASIC_IMPORT_GAOFEN3_CMD_CMD.SARSCAPEENVIRONMENT', 'IDL_ENVI_ENV'
  ob->SetParam, 'MAIN_BASIC_IMPORT_GAOFEN3_CMD_CMD.INPUT_FILE_LIST', [cfg.input_meta_xml]
  ob->SetParam, 'MAIN_BASIC_IMPORT_GAOFEN3_CMD_CMD.OUTPUT_FILE_LIST', [cfg.import_root]
  ob->SetParam, 'MAIN_BASIC_IMPORT_GAOFEN3_CMD_CMD.CROSS_COPOLARIZATION_FLAG', cfg.import_polarization_mode
  ob->SetParam, 'MAIN_BASIC_IMPORT_GAOFEN3_CMD_CMD.DOPP_ESTIMATION_FROM_RASTER_FLAG', 'OK'
  ob->SetParam, 'MAIN_BASIC_IMPORT_GAOFEN3_CMD_CMD.KEEP_ALL_LINES_FLAG', 'NotOK'
end


pro gf3_pipeline_set_multilook_params, ob
  compile_opt idl2
  common gf3_pipeline_cfg, cfg
  common gf3_pipeline_state, state

  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.SARSCAPEENVIRONMENT', 'IDL_ENVI_ENV'
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.INPUT_FILE_LIST', [state.current_input_root]
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.OUTPUT_FILE_LIST', [state.current_output_root]
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.MULTILOOK_METHOD', cfg.multilook_method
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.RANGE_MULTILOOK', gf3_float_str(cfg.range_looks)
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.AZIMUTH_MULTILOOK', gf3_float_str(cfg.azimuth_looks)
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.GRID_SIZE_FOR_SUGGESTED_LOOKS', gf3_float_str(cfg.grid_size_for_suggested_looks)
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.FILL_DUMMY_FLAG', 'OK'
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.FILL_DUMMY_METHOD', 'min_image_value'
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.ROWS_WINDOW_NUMBER', '3.0000000'
  ob->SetParam, 'MAIN_BASIC_MULTILOOKING.COLS_WINDOW_NUMBER', '3.0000000'
end


pro gf3_pipeline_set_filter_params, ob
  compile_opt idl2
  common gf3_pipeline_cfg, cfg
  common gf3_pipeline_state, state

  ob->SetParam, 'MAIN_BASIC_DESPECKLE_CONVENTIONAL_CMD.SARSCAPEENVIRONMENT', 'IDL_ENVI_ENV'
  ob->SetParam, 'MAIN_BASIC_DESPECKLE_CONVENTIONAL_CMD.INPUT_FILE_LIST', [state.current_input_root]
  ob->SetParam, 'MAIN_BASIC_DESPECKLE_CONVENTIONAL_CMD.OUTPUT_FILE_LIST', [state.current_output_root]
  ob->SetParam, 'MAIN_BASIC_DESPECKLE_CONVENTIONAL_CMD.FILT_TYPE', cfg.filter_type
  ob->SetParam, 'MAIN_BASIC_DESPECKLE_CONVENTIONAL_CMD.EQUIVALENT_LOOKS', '-1.0000000'
  ob->SetParam, 'PARAMETERS_GENERIC_FILTERS.WIN_SIZE', gf3_float_str(cfg.filter_window)
  ob->SetParam, 'PARAMETERS_GENERIC_FILTERS.ROWS_WINDOW_NUMBER', gf3_float_str(cfg.filter_window)
  ob->SetParam, 'PARAMETERS_GENERIC_FILTERS.COLS_WINDOW_NUMBER', gf3_float_str(cfg.filter_window)
  ob->SetParam, 'PARAMETERS_GENERIC_FILTERS.WIN_MODE_SIZE', gf3_float_str(cfg.filter_window)
end


pro gf3_pipeline_set_geocode_params, ob
  compile_opt idl2
  common gf3_pipeline_cfg, cfg
  common gf3_pipeline_state, state

  ob->SetParam, 'OUT_CARTOGRAPHIC_SYSTEM.OCS_CARTOGRAPHIC_SYSTEM_SPECIFICATION', ''
  ob->SetParam, 'OUT_CARTOGRAPHIC_SYSTEM.OCS_STATE', cfg.ocs_state
  ob->SetParam, 'OUT_CARTOGRAPHIC_SYSTEM.OCS_HEMISPHERE', cfg.ocs_hemisphere
  ob->SetParam, 'OUT_CARTOGRAPHIC_SYSTEM.OCS_PROJECTION', cfg.ocs_projection
  ob->SetParam, 'OUT_CARTOGRAPHIC_SYSTEM.OCS_ELLIPSOID', 'WGS84'
  ob->SetParam, 'OUT_CARTOGRAPHIC_SYSTEM.OCS_REFERENCE_HEIGHT', '0.0'

  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.SARSCAPEENVIRONMENT', 'IDL_ENVI_ENV'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.INPUT_FILE_LIST', [state.current_input_root]
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.OUTPUT_FILE_LIST', [state.current_output_root]
  if cfg.dem_file ne '' then ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.DEM_FILE_NAME', cfg.dem_file
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_GRID_SIZE_X', gf3_float_str(cfg.geocode_grid_x)
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_GRID_SIZE_Y', gf3_float_str(cfg.geocode_grid_y)
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_RESAMPLING_TYPE', cfg.geocode_resampling
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.CALIBRATION_FLAG', cfg.calibration_flag
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEO_SCATTERING_AREA_METHOD', 'sine_area_estimation'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.TRUE_AREA_EXPONENT', '1.0000000'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.MAX_VALUE_IN_CALIBRATION', '100.00000'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.RAD_NORMALIZATION_FLAG', cfg.rad_normalization_flag
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_RAD_NORM_DEG', '2.0000000'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_RAD_NORM_ANG', '-1.0000000'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_SIGMA_FLAG', cfg.output_sigma_flag
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_GAMMA_FLAG', cfg.output_gamma_flag
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_BETA_FLAG', cfg.output_beta_flag
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_COREG_IMAGES_FLAG', 'NotOK'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GENERATE_LIA_FLAG', 'NotOK'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.OUTPUT_TYPE', cfg.output_type
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.DUMMY_REMOVAL_FLAG', 'NotOK'
  ob->SetParam, 'MAIN_BASIC_CALIBRATION_AND_GEO_CMD.GEOCODE_BLOCK_SIZE', '30000.000'
end


pro gf3_init_default_cfg
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  cfg = { $
    input_meta_xml: 'C:\Users\Administrator\Desktop\GF3_Test\GF3_scene_20260513\GF3_SYC_FSI_051370_E124.6_N51.7_20260513_L1A_HHHV_L10007355955.meta.xml', $
    work_dir: 'C:\Users\Administrator\Desktop\GF3_Test\GF3_ENVI_IDL\work', $
    temp_dir: 'C:\Users\Administrator\Desktop\GF3_Test\GF3_ENVI_IDL\temp', $
    out_dir: 'C:\Users\Administrator\Desktop\GF3_Test\GF3_ENVI_IDL\out', $
    output_prefix: '', $
    dem_file: 'D:\DEM\COPDEM_GLO30_China_4326_DEM', $
    import_root: 'C:\Users\Administrator\Desktop\GF3_Test\GF3_ENVI_IDL\out\gf3_import', $
    import_polarization_mode: 'ALL_POL', $
    imported_hh_root: 'C:\Users\Administrator\Desktop\GF3_Test\GF3_ENVI_IDL\out\gaofer3_20260513_214340051_D_HH_slc', $
    imported_hv_root: 'C:\Users\Administrator\Desktop\GF3_Test\GF3_ENVI_IDL\out\gaofer3_20260513_214340051_D_HV_slc', $
    multilook_method: 'time_domain', $
    range_looks: 2.0, $
    azimuth_looks: 2.0, $
    grid_size_for_suggested_looks: 15.0, $
    filter_type: 'lee', $
    filter_window: 5.0, $
    geocode_grid_x: 15.0, $
    geocode_grid_y: 15.0, $
    geocode_resampling: '4th_order_cc', $
    calibration_flag: 'OK', $
    rad_normalization_flag: 'OK', $
    output_sigma_flag: 'OK', $
    output_gamma_flag: 'NotOK', $
    output_beta_flag: 'NotOK', $
    output_type: 'output_type_linear', $
    ocs_state: 'GEO-GLOBAL', $
    ocs_hemisphere: 'NONE', $
    ocs_projection: 'GEO' $
  }
end


pro gf3_configure, input_meta_xml=input_meta_xml, out_dir=out_dir, dem_file=dem_file, $
  work_dir=work_dir, temp_dir=temp_dir, range_looks=range_looks, $
  azimuth_looks=azimuth_looks, filter_type=filter_type, filter_window=filter_window, $
  geocode_grid_x=geocode_grid_x, geocode_grid_y=geocode_grid_y, $
  imported_hh_root=imported_hh_root, imported_hv_root=imported_hv_root

  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  gf3_init_default_cfg

  if n_elements(input_meta_xml) gt 0 then cfg.input_meta_xml = input_meta_xml
  if n_elements(out_dir) gt 0 then cfg.out_dir = out_dir
  if n_elements(dem_file) gt 0 then cfg.dem_file = dem_file
  if n_elements(work_dir) gt 0 then cfg.work_dir = work_dir
  if n_elements(temp_dir) gt 0 then cfg.temp_dir = temp_dir
  if n_elements(range_looks) gt 0 then cfg.range_looks = double(range_looks)
  if n_elements(azimuth_looks) gt 0 then cfg.azimuth_looks = double(azimuth_looks)
  if n_elements(filter_type) gt 0 then cfg.filter_type = filter_type
  if n_elements(filter_window) gt 0 then cfg.filter_window = double(filter_window)
  if n_elements(geocode_grid_x) gt 0 then cfg.geocode_grid_x = double(geocode_grid_x)
  if n_elements(geocode_grid_y) gt 0 then cfg.geocode_grid_y = double(geocode_grid_y)
  if n_elements(imported_hh_root) gt 0 then cfg.imported_hh_root = imported_hh_root
  if n_elements(imported_hv_root) gt 0 then cfg.imported_hv_root = imported_hv_root

  cfg.import_root = cfg.out_dir + '\gf3_import'
  cfg.output_prefix = gf3_scene_token(cfg.input_meta_xml)

  if n_elements(work_dir) eq 0 then cfg.work_dir = cfg.out_dir + '\work'
  if n_elements(temp_dir) eq 0 then cfg.temp_dir = cfg.out_dir + '\temp'

  if n_elements(imported_hh_root) eq 0 then cfg.imported_hh_root = ''
  if n_elements(imported_hv_root) eq 0 then cfg.imported_hv_root = ''
end


pro gf3_prepare_dirs
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  file_mkdir, cfg.work_dir
  file_mkdir, cfg.temp_dir
  file_mkdir, cfg.out_dir
end


pro gf3_start_batch
  compile_opt idl2
  common gf3_pipeline_cfg, cfg
  SARscape_Batch_Init, Temp_Directory=cfg.temp_dir
end


pro gf3_stop_batch
  compile_opt idl2
  SARscape_Batch_Exit
end


pro gf3_run_import, errmsg=errmsg
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  errmsg = ''
  gf3_run_module, 'ImportGaofen3', 'gf3_pipeline_set_import_params', errmsg=errmsg, working_directory=cfg.work_dir
end


pro gf3_run_multilook, polarization, errmsg=errmsg
  compile_opt idl2
  common gf3_pipeline_cfg, cfg
  common gf3_pipeline_state, state

  state = {current_input_root: gf3_base_root(polarization), current_output_root: gf3_stage_root(polarization, 'multilook')}
  errmsg = ''
  gf3_run_module, 'BaseMultilooking', 'gf3_pipeline_set_multilook_params', errmsg=errmsg, working_directory=cfg.work_dir
end


pro gf3_run_filter, polarization, errmsg=errmsg
  compile_opt idl2
  common gf3_pipeline_cfg, cfg
  common gf3_pipeline_state, state

  state = {current_input_root: gf3_stage_root(polarization, 'multilook'), current_output_root: gf3_stage_root(polarization, 'filter')}
  errmsg = ''
  gf3_run_module, 'DespeckleConventionalSingle', 'gf3_pipeline_set_filter_params', errmsg=errmsg, working_directory=cfg.work_dir
end


pro gf3_run_geocode, polarization, errmsg=errmsg
  compile_opt idl2
  common gf3_pipeline_cfg, cfg
  common gf3_pipeline_state, state

  state = {current_input_root: gf3_stage_root(polarization, 'filter'), current_output_root: gf3_stage_root(polarization, 'geocode')}
  errmsg = ''
  gf3_run_module, 'BasicGeocoding', 'gf3_pipeline_set_geocode_params', errmsg=errmsg, working_directory=cfg.work_dir
end


pro gf3_run_single_pol_pipeline, polarization, do_import=do_import, errmsg=errmsg
  compile_opt idl2

  errmsg = ''
  if keyword_set(do_import) then begin
    gf3_run_import, errmsg=errmsg
    if errmsg ne '' then return
    gf3_refresh_import_roots
  endif

  gf3_run_multilook, polarization, errmsg=errmsg
  if errmsg ne '' then return

  gf3_run_filter, polarization, errmsg=errmsg
  if errmsg ne '' then return

  gf3_run_geocode, polarization, errmsg=errmsg
end


function gf3_should_run_pol, polarizations, polarization
  compile_opt idl2

  if n_elements(polarizations) eq 0 then return, 1

  wanted = strupcase(strtrim(polarizations, 2))
  pol = strupcase(strtrim(polarization, 2))

  for i = 0, n_elements(wanted) - 1 do begin
    if wanted[i] eq 'ALL' then return, 1
    if wanted[i] eq pol then return, 1
  endfor

  return, 0
end


pro gf3_sarscape_run, input_meta_xml=input_meta_xml, out_dir=out_dir, dem_file=dem_file, $
  polarizations=polarizations, skip_import=skip_import, work_dir=work_dir, temp_dir=temp_dir, $
  range_looks=range_looks, azimuth_looks=azimuth_looks, filter_type=filter_type, $
  filter_window=filter_window, geocode_grid_x=geocode_grid_x, geocode_grid_y=geocode_grid_y

  compile_opt idl2

  gf3_configure, input_meta_xml=input_meta_xml, out_dir=out_dir, dem_file=dem_file, $
    work_dir=work_dir, temp_dir=temp_dir, range_looks=range_looks, $
    azimuth_looks=azimuth_looks, filter_type=filter_type, filter_window=filter_window, $
    geocode_grid_x=geocode_grid_x, geocode_grid_y=geocode_grid_y

  gf3_prepare_dirs
  gf3_start_batch

  errmsg = ''

  if ~keyword_set(skip_import) then begin
    gf3_run_import, errmsg=errmsg
    if errmsg eq '' then gf3_refresh_import_roots
  endif else begin
    gf3_refresh_import_roots
  endelse

  if errmsg eq '' && gf3_should_run_pol(polarizations, 'HH') then gf3_run_single_pol_pipeline, 'HH', errmsg=errmsg
  if errmsg eq '' && gf3_should_run_pol(polarizations, 'HV') then gf3_run_single_pol_pipeline, 'HV', errmsg=errmsg

  gf3_stop_batch
  if errmsg ne '' then print, 'Pipeline stopped: ' + errmsg
end


pro gf3_sarscape_pipeline
  compile_opt idl2
  common gf3_pipeline_cfg, cfg

  gf3_init_default_cfg
  gf3_prepare_dirs
  gf3_start_batch

  errmsg = ''
  gf3_run_import, errmsg=errmsg
  if errmsg eq '' then gf3_refresh_import_roots
  if errmsg eq '' then gf3_run_single_pol_pipeline, 'HH', errmsg=errmsg
  if errmsg eq '' then gf3_run_single_pol_pipeline, 'HV', errmsg=errmsg

  gf3_stop_batch
  if errmsg ne '' then print, 'Pipeline stopped: ' + errmsg
end


pro gf3_sarscape_import_only
  compile_opt idl2

  gf3_init_default_cfg
  gf3_prepare_dirs
  gf3_start_batch
  errmsg = ''
  gf3_run_import, errmsg=errmsg
  gf3_stop_batch
  if errmsg ne '' then print, 'Import stopped: ' + errmsg
end


pro gf3_sarscape_hh_only
  compile_opt idl2

  gf3_init_default_cfg
  gf3_prepare_dirs
  gf3_start_batch
  errmsg = ''
  gf3_run_single_pol_pipeline, 'HH', do_import=1, errmsg=errmsg
  gf3_stop_batch
  if errmsg ne '' then print, 'HH pipeline stopped: ' + errmsg
end


pro gf3_sarscape_hv_only
  compile_opt idl2

  gf3_init_default_cfg
  gf3_prepare_dirs
  gf3_start_batch
  errmsg = ''
  gf3_run_single_pol_pipeline, 'HV', do_import=1, errmsg=errmsg
  gf3_stop_batch
  if errmsg ne '' then print, 'HV pipeline stopped: ' + errmsg
end
