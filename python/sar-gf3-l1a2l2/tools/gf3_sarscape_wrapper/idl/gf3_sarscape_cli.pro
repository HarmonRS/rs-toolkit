function gf3_cli_split_csv, value
  compile_opt idl2

  text = strtrim(value, 2)
  if text eq '' then return, ['HH', 'HV']

  parts = ['']
  first = 1
  while 1 do begin
    pos = strpos(text, ',')
    if pos lt 0 then begin
      token = strtrim(text, 2)
      if first then parts = [token] else parts = [parts, token]
      break
    endif
    token = strtrim(strmid(text, 0, pos), 2)
    if first then begin
      parts = [token]
      first = 0
    endif else begin
      parts = [parts, token]
    endelse
    text = strtrim(strmid(text, pos + 1), 2)
  endwhile

  return, parts
end


pro gf3_sarscape_cli
  compile_opt idl2

  args = command_line_args(count=argc)
  if argc lt 3 then begin
    print, 'Usage: idlrt.exe gf3_sarscape_cli.sav -args input_meta_xml out_dir dem_file [polarizations]'
    print, 'Example polarizations: HH,HV or HH or HV'
    return
  endif

  input_meta_xml = args[0]
  out_dir = args[1]
  dem_file = args[2]
  file_mkdir, out_dir

  log_file = out_dir + '\gf3_sarscape_cli.log'
  openw, lun, log_file, /get_lun
  catch, err
  if err ne 0 then begin
    printf, lun, 'ERROR: ', !error_state.msg
    free_lun, lun
    catch, /cancel
    return
  endif

  printf, lun, 'CLI start'
  printf, lun, 'input_meta_xml=', input_meta_xml
  printf, lun, 'out_dir=', out_dir
  printf, lun, 'dem_file=', dem_file

  if argc ge 4 then begin
    polarizations = gf3_cli_split_csv(args[3])
  endif else begin
    polarizations = ['HH', 'HV']
  endelse

  printf, lun, 'polarizations=', strjoin(polarizations, ',')

  e = envi(/headless)
  printf, lun, 'ENVI headless initialized'

  gf3_sarscape_run, $
    input_meta_xml=input_meta_xml, $
    out_dir=out_dir, $
    dem_file=dem_file, $
    polarizations=polarizations

  printf, lun, 'CLI end'
  free_lun, lun
end
