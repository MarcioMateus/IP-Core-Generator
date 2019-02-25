#!/usr/bin/env python3

import os, sys, glob, subprocess, json, time, shutil, errno, pathlib
import settings, repository
import websocket
from xml.dom import expatbuilder
from repository import ANSI_RED, ANSI_GREEN, ANSI_YELLOW, ANSI_BLUE, ANSI_MAGENTA, ANSI_CYAN, ANSI_END

# IP Core Generator Source Name
repository_ipcoregen_source = "ipcore-generator"

# Temporary Directories
tempdir = "_tmp/"
generated_ipcore_dir = "generated-ipcores"
generated_src_dir = "generated-src"



def main():

	#Remove temporary directories
	if os.path.isdir(generated_ipcore_dir):
		shutil.rmtree(generated_ipcore_dir)
	if os.path.isdir(generated_src_dir):
		shutil.rmtree(generated_src_dir)	
	if os.path.isdir(tempdir):
		shutil.rmtree(tempdir)
	os.mkdir(tempdir)


	# Usage
	if len(sys.argv) < 2:
		print("Usage: {} [mode] <args for mode>".format(sys.argv[0]))
		print("Valid modes are: subscribe, remote, local, upload, download, verify, listdeps, clean")
		sys.exit(1)


	# Subscribe
	elif sys.argv[1] == 'subscribe':
		"""
		Subscribe to a project using the Application Manager. Waits for updates to the project and
		analyses any checked deployments continually.
		Arguments:
			[2] - project name to subscribe to
		"""
		if len(sys.argv) < 3:
			print("Usage: {} subscribe <model-name>".format(sys.argv[0]))
			sys.exit(1)
		
		repository.set_project(sys.argv[2])
		repository.set_source(settings.repository_user_dir)
		subscribe(sys.argv[2], settings.repository_descriptions_dir, tempdir)

	# Remote
	elif sys.argv[1] == 'remote':
		"""
		Download all files from the repository found in a given path, then perform analysis on it.
		Arguments:
			[2] - repository path to the file to download (including filename)
		"""
		if len(sys.argv) < 3:
			print("Usage: {} remote <project-name>".format(sys.argv[0]))
			sys.exit(1)

		repository.set_project(sys.argv[2])
		repository.set_source(settings.repository_user_dir)
		repository.downloadFiles(settings.repository_descriptions_dir, tempdir)
		local_mode(tempdir, tempdir, False)

	# Local
	elif sys.argv[1] == 'local':
		"""
		Analyse a folder of XML files.
		Arguments:
			[2] - path to folder to analyse
			[3] - path to folder to write outputs to
		"""
		if len(sys.argv) < 4:
			print("Usage: {} local <input-model-dir> <output-dir>".format(sys.argv[0]))
			sys.exit(1)
		inputdir = repository.enforce_trailing_slash(sys.argv[2])
		outputdir = repository.enforce_trailing_slash(sys.argv[3])
		local_mode(inputdir, outputdir, None, None, True)

	# Source
	elif sys.argv[1] == 'source':
		"""
		Run the IP Core Generator on local source files
		Arguments:
			[2] - path to folder to analyse
			[3] - source filename
			[4] - header filename
			[5] - top function name
			[6] - solution name
			[7] - output directory
		"""
		if len(sys.argv) < 8:
			print("Usage: {} source <source-dir> <source-filename> <header-filename> <top-funtion> <solution-name> <output-dir>"
				.format(sys.argv[0]))
			sys.exit(1)
		srcdir = repository.enforce_trailing_slash(sys.argv[2])
		outputdir = repository.enforce_trailing_slash(sys.argv[7])
		source_mode(srcdir, sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], outputdir)

	# Upload
	elif sys.argv[1] == 'upload':
		"""
		Upload a file to the Repository.
		Arguments:
			[2] - path to the file to upload
			[3] - project name in the repository
			[4] - repository source name
			[5] - path in the repository to upload to (including filename)
			[6] - what to set the "data_type" metadata to
			[7] - what to set the "checked" metadata to
		"""
		if len(sys.argv) < 6:
			print("Usage: {} upload <source-file> <project-name> <source-name> <destpath> <data-type> <checked>"
				.format(sys.argv[0]))
			sys.exit(1)

		repository.set_project(sys.argv[3])
		repository.set_source(sys.argv[4])
		repository.uploadFile(sys.argv[2], sys.argv[5], sys.argv[6], sys.argv[7])
		print("Upload complete.")

	# Download
	elif sys.argv[1] == 'download':
		"""
		Download a file from the Repository.
		Arguments:
			[2] - project name in the repository
			[3] - repository source name
			[4] - path to the file to download (including filename)
			[5] - local path (including filename) to save the file as
		"""
		if len(sys.argv) < 4:
			print("Usage: {} download <project-name> <source-name> <file> <output-file>".format(sys.argv[0]))
			sys.exit(1)

		repository.set_project(sys.argv[2])
		repository.set_source(sys.argv[3])
		repository.downloadFile(sys.argv[4], sys.argv[5])
		print("Download complete.")
			
	# Verify
	elif sys.argv[1] == 'verify':
		"""
		Check if we can see the other tools.
		"""
		rc = subprocess.call(['which', 'vivado_hls'], stdout=subprocess.PIPE)
		if rc == 0:
			print('Xilinx tools - OK')
		else:
			print(ANSI_RED + 'Missing Xilinx tools!' + ANSI_END)
			print('Please check if Vivado is installed and accessible.')
			sys.exit(1)

		repository.authenticate()
		print('Repository is assessible - OK')

		print("All Dependencies tests passed.")
		sys.exit(0)

	# List Deployments
	elif sys.argv[1] == 'listdeps':
		"""
		List all deployments in the given path.
		Arguments:
			[2] - project name in the repository to search for deployments
		"""

		
		repository.set_project(sys.argv[2])
		repository.set_source(settings.repository_user_dir)
		repository.listDeployments(settings.repository_descriptions_dir)

	# Clean
	elif sys.argv[1] == 'clean':
		"""
		Deletes temporary files and folders
		"""
		if os.path.isdir(tempdir):
			shutil.rmtree(tempdir)
		if os.path.isdir(generated_ipcore_dir):
			shutil.rmtree(generated_ipcore_dir)
		if os.path.isdir(generated_src_dir):
			shutil.rmtree(generated_src_dir)

	else:
		print("Invalid mode.")
		print("Valid modes are: subscribe, remote, local, upload, download, verify, listdeps, clean")
		sys.exit(1)
	
	# Delete temporary files on exit
	if os.path.isdir(tempdir):
		shutil.rmtree(tempdir)



def local_mode(inputdir, outputdir, uploadoncedone, models = None, localmode = False):
	"""
	Read the model from inputdir, creating all output files into outputdir.
	If uploadoncedone, then the metadata in the repository is updated for each
	deployment tested according to the result.

	models should be a dictionary of the form:
	{ 'cn': 'filename.xml', 'pd': 'filename.xml', ['de': 'filename.xml'] }
	Otherwise the input directory will be searched for files that start with 'cn', 'pd', and 'de' respectively and will
	fail if they are not found, and apart from deployments, unique.
	
	If multiple deployments are found/specified they are all tested.

	inputdir and outputdir can be the same location.
	"""

	if models == None:
		models = find_input_models(inputdir)
		if len(models['de']) > 0:
			print(ANSI_CYAN + "Found {} deployments to process.\n".format(
				len(models['de']), "s" if len(models['de']) > 1 else "") + ANSI_END)

	#Prepare output directory
	os.makedirs(outputdir, exist_ok=True)

	#Now run an analysis for each deployment
	for dep in models['de']:
		print(ANSI_YELLOW + "Processing model: {} {} {}".format(os.path.basename(models['cn']),
			os.path.basename(models['pd']),	os.path.basename(dep)) + ANSI_END)
		#summarise_deployment(dep)
		ipcore_generator(dep, models['cn'], inputdir, outputdir, localmode)

	if len(models) == 0:
		print(ANSI_RED + "No valid deployments found." + ANSI_END)



def subscribe(repository_projectname, path, tempdir):
	"""
	Subscribe to a project using the Application Manager. Waits for updates to the project and
	analyses any checked deployments continually.
	"""
	def checkForUDs(path, tempdir):
		import time
		time.sleep(1) # We currently seem to have to give the metadata a little time to update inside the repository
		uds = repository.checkedDeployments(path)

		if(len(uds) > 0):
			print(ANSI_GREEN + "Project has {} checked deployment{}...\n".format(
				len(uds), "s" if len(uds) > 1 else "") + ANSI_END)

			# Download the files
			models = {} # This will tell local_mode which XML files are of which type

			cns = repository.downloadAllFilesOfType("componentnetwork", path, tempdir)
			if len(cns) != 1:
				print(ANSI_RED + "Multiple files of type 'componentnetwork' \
				found at path {} when only one was expected.".format(path) + ANSI_END)
				sys.exit(1)
			models['cn'] = os.path.join(tempdir, cns[0])

			pds = repository.downloadAllFilesOfType("platformdescription", path, tempdir)
			if len(pds) != 1:
				print(ANSI_RED + "Multiple files of type 'platformdescription' \
				found at path {} when only one was expected.".format(path) + ANSI_END)
				sys.exit(1)
			models['pd'] = os.path.join(tempdir, pds[0])
			
			deps = []
			for dep in uds:
				deps.extend([os.path.join(tempdir, dep['filename'])])
				repository.downloadFile(os.path.join(path, dep['filename']), 
					os.path.join(tempdir, dep['filename']), True, False)
			models['de'] = deps

			local_mode(tempdir, tempdir, path, models=models)

	print(ANSI_GREEN + "Subscribing to folder {}/{} of project {}. Waiting for updates..."
		.format(settings.repository_user_dir, path, repository_projectname) + ANSI_END)
	
	try:
		ws = websocket.create_connection("ws://{}:{}".format(settings.app_manager_ip, settings.app_manager_port))
		req = "{{\"user\":\"{}\" , \"project\":\"{}\"}}".format(settings.repository_user, repository_projectname)
		ws.send(req)
		result = ws.recv()
	except ConnectionRefusedError:
		print(ANSI_RED + "Cannot connect to Application Manager." + ANSI_END)
		print("Response: {}".format(result)) if 'result' in locals() else None
		sys.exit(1)

	try:
		reply = json.loads(result)
		if not 'suscribed_to_project' in reply:
			raise json.decoder.JSONDecodeError
	except json.decoder.JSONDecodeError:
		print(ANSI_RED + "Invalid response from Application Manager. Response: {}".format(result))
		sys.exit(1)

	# Run a first check regardless of response from the websocket
	checkForUDs(path, tempdir)

	while True:
		try:
			result = ws.recv()
			reply = json.loads(result)

			if 'project' in reply and reply['project'] == repository_projectname:
				checkForUDs(path, tempdir)
		except json.decoder.JSONDecodeError:
			print(ANSI_RED + "Invalid response from Application Manager. Response: {}".format(result))
			sys.exit(1)



def find_input_models(inputdir):
	'''
	Determine input models as:
	{
		'cn': <inputdir>cn*.xml,
		'pd': <inputdir>pd*.xml,
		['de': <inputdir>de*.xml]
	}
	'''
	def deglob_input_models(pattern):
		'''
		Turn the provided pattern into an absolute filename. Also checks that the de-globbing is unique and
		outputs an error and exits if not.
		'''
		results = glob.glob(pattern)
		if(len(results) != 1):
			print("The pattern {} does not refer to a unique file.".format(pattern))
			sys.exit(1)
		else:
			return results[0]

	models = {
		'cn': deglob_input_models("{}cn*.xml".format(inputdir)),
		'pd': deglob_input_models("{}pd*.xml".format(inputdir))
	}

	models['de'] = glob.glob("{}de*.xml".format(inputdir))

	if len(models['de']) < 1:
		print("Cannot find deployments in project {}".format(repository.get_project()))
		sys.exit(1)
	return models



def summarise_deployment(filename):
	print(ANSI_MAGENTA + "Mappings:")
	doc = expatbuilder.parse(filename, False)
	mappings = doc.getElementsByTagName('mapping')
	for m in mappings:
		comp = m.getElementsByTagName('component')
		proc = m.getElementsByTagName('processor')
		if len(comp) == 1 and len(proc) == 1:
			print("\t{} -> {}".format(comp[0].getAttribute('name'), proc[0].getAttribute('name')))
	print(ANSI_END)
	
	
	
def source_mode(srcdir, srcfile, headerfile, top_function, solution_name, outputdir):
	ipcore_zip = os.path.join(generated_ipcore_dir, "{}.zip".format(solution_name))
	drivers_dir = os.path.join(generated_ipcore_dir, solution_name , "impl", "ip", "drivers", top_function+"_top_v1_0", "src")
	os.makedirs(generated_src_dir, exist_ok=True)
	copytree(srcdir, generated_src_dir)
	
	# Transform source code, generate IP Core and create modified software component
	exitcode = generateIPcore(generated_src_dir, srcfile, headerfile, top_function, solution_name)
	
	if exitcode == 0:
		# ZIP IP Core
		exitcode = os.system("cd " + generated_ipcore_dir + "/ && zip -r {}.zip {}/ > ../zip.log && cd - > /dev/null"
			.format(solution_name, solution_name))

	if exitcode == 0:
		print(ANSI_GREEN + "\nIP Core Generation Finished" + ANSI_END)

		ipcore_zip = os.path.join(generated_ipcore_dir, "{}.zip".format(solution_name))
		drivers_dir = os.path.join(generated_ipcore_dir, solution_name , "impl", "ip", "drivers",
			 top_function+"_top_v1_0", "src")

		# save Outputs
		print(ANSI_CYAN + "\nSaving files to output dir..." + ANSI_END)
		os.makedirs(os.path.join(outputdir, solution_name, "drivers"), exist_ok=True)
		copy(ipcore_zip, os.path.join(outputdir, solution_name))
		copytree(generated_src_dir, os.path.join(outputdir, solution_name))
		copytree(drivers_dir, os.path.join(outputdir, solution_name, "drivers"))	
		print(ANSI_GREEN + "\nFinished" + ANSI_END)
	else:
		print(ANSI_RED + "\nIP Core Generation Failed - exitcode: {}".format(exitcode) + ANSI_END)
		
	# Delete Temporary Files
	if os.path.isdir(generated_ipcore_dir):
		shutil.rmtree(generated_ipcore_dir)
	if os.path.isdir(generated_src_dir):
		shutil.rmtree(generated_src_dir)	
	if os.path.isdir(tempdir):
		shutil.rmtree(tempdir)



def ipcore_generator(componentNetwork, inputdir, outputdir, localmode):
	# Parse Deployment Plan and Component Network
	for fpga_component in getFPGAcomponentsFromCN(componentNetwork):
		tmpdir = getfilesfromCN(componentNetwork, fpga_component, localmode, inputdir)
        
        #TODO Not be the best way to get the file names
		top_function = "{}".format(fpga_component)
		src_file = os.path.relpath(os.path.join(tmpdir,"{}.cpp".format(fpga_component)),generated_src_dir)
		header_file = os.path.relpath(os.path.join(tmpdir,"{}.h".format(fpga_component)),generated_src_dir)
        
		timestamp = int(time.time())
		solution_name = "{}-{}".format(top_function, timestamp)

		# IP Core Generator Start
		print(ANSI_CYAN + "\nPHANTOM IP CORE GENERATOR" + ANSI_END)
		print(ANSI_BLUE + "\tSolution: \t"     + ANSI_END + solution_name)
		print(ANSI_BLUE + "\tTop function: \t" + ANSI_END + top_function)
		print(ANSI_BLUE + "\tSource File: \t"  + ANSI_END + src_file)
		print(ANSI_BLUE + "\tHeader File: \t"  + ANSI_END + header_file)

		os.makedirs(generated_src_dir, exist_ok=True)
		
		# Transform source code, generate IP Core and create modified software component
		exitcode = generateIPcore(generated_src_dir, src_file, header_file, top_function, solution_name)

		if exitcode == 0:
			# ZIP IP Core
			exitcode = os.system("cd " + generated_ipcore_dir + "/ && zip -r {}.zip {}/ > ../zip.log && cd - > /dev/null"
				.format(solution_name, solution_name))

		if exitcode == 0:
			print(ANSI_GREEN + "\nIP Core Generation Finished" + ANSI_END)

			ipcore_zip = os.path.join(generated_ipcore_dir, "{}.zip".format(solution_name))
			drivers_dir = os.path.join(generated_ipcore_dir, solution_name , "impl", "ip", "drivers",
				 top_function+"_top_v1_0", "src")

			# Add new implementation to Component Network
			files = [generated_src_dir, drivers_dir, ipcore_zip]
			cn = addfilestoCN(componentNetwork, fpga_component, files, solution_name)

			# Upload to Repository or save locally
			if localmode == True:
				print(ANSI_CYAN + "\nSaving files to output dir..." + ANSI_END)
				os.makedirs(os.path.join(outputdir, solution_name, "drivers"), exist_ok=True)
				copy(ipcore_zip,os.path.join(outputdir, solution_name))
				copytree(generated_src_dir, os.path.join(outputdir, solution_name))
				copytree(drivers_dir, os.path.join(outputdir, solution_name, "drivers"))
				copy(componentNetwork, outputdir)
			else:
				print(ANSI_CYAN + "\nUploading files to Repository..." + ANSI_END)
				repository.uploadIPCoreZip(ipcore_zip, solution_name, "zip", top_function)
				repository.uploadDir(generated_src_dir, solution_name, "cpp")
				repository.uploadDir(drivers_dir, os.path.join(solution_name, "drivers"))
				repository.set_source(settings.repository_user_dir)
				repository.uploadFile(componentNetwork, settings.repository_descriptions_dir, "componentnetwork")

			print(ANSI_GREEN + "\nFinished" + ANSI_END)
		else:
			print(ANSI_RED + "\nIP Core Generation Failed - exitcode: {}".format(exitcode) + ANSI_END)

	# Delete Temporary Files
	repository.set_source(settings.repository_user_dir)
	if os.path.isdir(generated_ipcore_dir):
		shutil.rmtree(generated_ipcore_dir)
	if os.path.isdir(generated_src_dir):
		shutil.rmtree(generated_src_dir)	
	if os.path.isdir(tempdir):
		shutil.rmtree(tempdir)
	os.mkdir(tempdir)



def generateIPcore(srcdir, srcfile, headerfile, topfunction, solution_name):
	# Tranform source code
	print(ANSI_CYAN + "\nTransforming source code..." + ANSI_END)
	transformed_src = os.path.join(os.path.abspath(srcdir), srcfile)
	transformed_src_ip = os.path.join(os.path.abspath(srcdir), os.path.splitext(srcfile)[0] +"-ip"+ os.path.splitext(srcfile)[1])
		
	exitcode = os.system("./ipcore-rewriter " + os.path.join(srcdir, srcfile) + " " + transformed_src_ip)
	if not exitcode == 0:
		print(ANSI_RED + "Source code transformation failed!" + ANSI_END)
		return exitcode

	# Generate IP Core
	print(ANSI_CYAN + "\nGenerating IP Core..." + ANSI_END)
	exitcode = os.system("vivado_hls script.tcl -tclargs {} {} {} {} {}".format(settings.target_fpga, 
		solution_name, topfunction, transformed_src_ip, os.path.join(srcdir, headerfile)))
		
	os.remove(transformed_src_ip)

	if not exitcode == 0:
		print(ANSI_RED + "IP Core Generation failed!" + ANSI_END)
		return exitcode
	else:
		print(ANSI_GREEN + "\nSuccess" + ANSI_END)
		print(ANSI_BLUE + "\tSolution: {}".format(solution_name) + ANSI_END)

	# Create modified software component
	print(ANSI_CYAN + "\nCreating modified software component with IP Core adapter..." + ANSI_END)
	exitcode = os.system("./ipcore-arm-adapter " + os.path.join(srcdir, srcfile) + " " + transformed_src)

	if not exitcode == 0:
		print(ANSI_RED + "Modified software component creation failed!" + ANSI_END)
	return exitcode



# Parse Deployment Plan	and get components mapped to FPGAs
def getFPGAcomponentsFromDP(deploymentPlan):
	print(ANSI_MAGENTA + "\nMappings:")
	fpga_components = []
	dp = expatbuilder.parse(deploymentPlan, False)
	mappings = dp.getElementsByTagName('mapping')

	for m in mappings:
		comp = m.getElementsByTagName('component')
		proc = m.getElementsByTagName('processor')

		if len(comp) == 1 and len(proc) == 1:
			print("\t{} -> {}".format(comp[0].getAttribute('name'), proc[0].getAttribute('name')))

		if proc[0].getAttribute('name') == "FPGA":
			fpga_components.append(comp[0].getAttribute('name'))
	print()
	return fpga_components

	
	
# Parse Component Network and get components with FPGA target
def getFPGAcomponentsFromCN(componentNetwork):
	print(ANSI_CYAN + "\nMappings:"+ANSI_END)
	fpga_components = []
	dp = expatbuilder.parse(componentNetwork, False)
	mappings = dp.getElementsByTagName('component')

	for m in mappings:
		devices = m.getElementsByTagName('devices')

		if len(devices) == 1:
			if  devices[0].getAttribute('FPGA').lower() == 'yes':
				print(ANSI_GREEN,end="")
				fpga_components.append(m.getAttribute('name'))
			else:
				print(ANSI_BLUE,end="")
			
			print("\t{:<15} ".format(m.getAttribute('name')),end="")	
			print(ANSI_BLUE+"CPU -> {:<5} GPU -> {:<5} ".format(devices[0].getAttribute('CPU'),
				devices[0].getAttribute('GPU')),end="")
			
			if  devices[0].getAttribute('FPGA').lower() == 'yes':
				print(ANSI_GREEN,end="")
			else:
				print(ANSI_BLUE,end="")
					
			print("FPGA -> {:<5}".format(devices[0].getAttribute('FPGA')))
			
	print(ANSI_END)
	return fpga_components
	


# Parse Component Network and get files for the specified component
def getfilesfromCN(componentNetwork, fpga_component, localmode, inputdir):
	cn = expatbuilder.parse(componentNetwork, False)
	components = cn.getElementsByTagName('component')

	directories = []
	for component in components:
		if component.getAttribute('name') == fpga_component:
			implementations = component.getElementsByTagName('implementation')
			for implementation in implementations:
				if implementation.getAttribute('id') == "1":
					source_files = implementation.getElementsByTagName('source')
					for source_file in source_files:
						if source_file.getAttribute('path') not in directories:
							directories.append(source_file.getAttribute('path'))
	
	#TODO Not be the best way to get the main component directory.
	firstdir = tmpdir = os.path.join(generated_src_dir,directories[0])
	
	# Get Files
	for ddir in directories:
		if localmode == True:
			localdir = os.path.abspath(os.path.join(inputdir, ddir))
			tmpdir = os.path.join(generated_src_dir, ddir)
			os.makedirs(tmpdir, exist_ok=True)
			copytree(localdir, tmpdir)
		else:			
			repository.set_source(settings.repository_user_dir)
			tmpdir = os.path.join(generated_src_dir, ddir)
			os.makedirs(tmpdir, exist_ok=True)
			repository.downloadFiles(ddir, tmpdir)
			repository.set_source(repository_ipcoregen_source)
	return firstdir



# Add new files to Component Network
def addfilestoCN(componentNetwork, fpga_component, files, path):
	cn = expatbuilder.parse(componentNetwork, False)

	for component in cn.getElementsByTagName('component'):
		if component.getAttribute('name') == fpga_component:
			newimpl = cn.createElement("implementation")
			newimpl.setAttribute("target", "fpga")
			newimpl.setAttribute("id", "3")
			
			# Modified component files
			relpath, filename = os.path.split(files[0])
			newsrc = cn.createElement("source")
			newsrc.setAttribute("file", filename)
			newsrc.setAttribute("lang", "".join(pathlib.Path(files[0]).suffixes))
			newsrc.setAttribute("path", path)
			newimpl.appendChild(newsrc)

			for root, directories, filenames in os.walk(files[1]):
				for filename in filenames:
					filepath = os.path.join(files[1], filename)
					if os.path.isfile(filepath): 
						relpath, filename = os.path.split(filepath)
						newsrc = cn.createElement("source")
						newsrc.setAttribute("file", filename)
						newsrc.setAttribute("lang", "".join(pathlib.Path(filename).suffixes)[1:])
						newsrc.setAttribute("path", os.path.join(path, "drivers"))
						newimpl.appendChild(newsrc)
					else:
						print("{} is not a valid file.".format(filepath))
			
			# IP Core Zip
			relpath, filename = os.path.split(files[2])
			newsrc = cn.createElement("source")
			newsrc.setAttribute("file", filename)
			newsrc.setAttribute("lang", "ipcore")
			newsrc.setAttribute("path", path)
			newimpl.appendChild(newsrc)
			
			# Write XML
			component.appendChild(newimpl)
			cnstring = cn.toprettyxml().replace("\r", "").replace("\n", "")
			cn = expatbuilder.parseString(cnstring, False)
			f = open(componentNetwork, "w+")
			cn.writexml(f, "", "\t", "\n")
			f.close()
	return cn



def copy(src, dest):
	try:
		copytree(src, dest)
	except OSError as e:
		# If the error was caused because the source wasn't a directory
		if e.errno == errno.ENOTDIR:
			shutil.copy2(src, dest)
		else:
			print('Directory not copied. Error: %s' % e)



def copytree(src, dst, symlinks=False, ignore=None):
	if not os.path.exists(dst):	
		os.makedirs(dst, exist_ok=True)
	if not os.path.isdir(src):
		shutil.copy2(src, dst)
	else:
		for item in os.listdir(src):
			s = os.path.join(src, item)
			d = os.path.join(dst, item)
			if os.path.isdir(s):
				shutil.copytree(s, d, symlinks, ignore)
			else:
				shutil.copy2(s, d)
		


if __name__ == "__main__":
	main()


