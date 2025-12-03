import logging
import os

import vtk
import pathlib
from pathlib import Path
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import ctk
import qt
from datetime import datetime
import SegmentStatistics
import logging
import re
#from qt import QtCore, QtGui

try:
    import pandas as pd
    import numpy as np
    import SimpleITK as sitk
except:
    slicer.util.pip_install('pandas')
    slicer.util.pip_install('numpy')
    slicer.util.pip_install('SimpleITK')
    
    import pandas as pd
    import numpy as np
    import SimpleITK as sitk
#
# SegmentationReview
#
#remove warnings
import warnings
warnings.filterwarnings("ignore")

class CEMArtifacts(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CEM Artifacts review"  
        self.parent.categories = ["Examples"]  
        self.parent.dependencies = []  
        self.parent.contributors = ["Donna Hooft;Valentina Corbetta"]  
        self.parent.helpText = """
Slicer3D extension for assesing presence of artifacts on recombined Contrast Enhanced Mammography (CEM) images and 
for segmentation of Artifacts which are not locally bound.
       """
        self.parent.acknowledgementText = """
This file was developed by Donna Hooft based on a github repository created by Anna Zapaishchykova and Vasco Prudente. 
"""
       


#
# CEMArtifactsWidget
#

class CEMArtifactsWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False


        # Changed to store pairs of volumes (DM and CM)
        self.volume_pairs = {}  # Maps view tag (e.g., "P1_L_CC") to {"DM": node, "CM": node}
        self.segmentation_node = None
        
        self.image_pairs = []  # List of paired image info dicts
        self.directory = None
        self.current_index = 0
        self.likert_scores = []
        self.n_pairs = 0
        
        

        self.volume_node = None
        self.nifti_files = []
        self.segmentation_files = []
        self.n_files = 0
        self.seg_mask_status = [] # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded, 3- mask edited
        self.with_mapper_flag = False
        self.id_subs = []
        self.id_subs_checked = []
        self.unique_case_flag=False
        self.finish_flag = False


        self.pointListNode = None
        self.window_level = None   # To store current window/level settings
        self.segment_visiblity_states = {}  # Dictionary to store the visibility toggle of each segment
        self._is_loading = False # Flag to prevent re-entrance during loading





    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        import qSlicerSegmentationsModuleWidgetsPythonQt
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CEMArtifacts.ui'))
        # --- Enable/disable artifact checkboxes based on Yes/No selection ---
        
        
        # Layout within the collapsible button
        parametersCollapsibleButton = ctk.ctkCollapsibleButton()
        parametersCollapsibleButton.text = "Input path" #establishes collapasbale button for input path
        self.layout.addWidget(parametersCollapsibleButton)

        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)
        self.atlasDirectoryButton = ctk.ctkDirectoryButton() #lets you select path for pictures
        parametersFormLayout.addRow("Directory: ", self.atlasDirectoryButton) #Buttons for input path
        
        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)
        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = SlicerLikertDLratingLogic()

        # Connections
        #shortcut = qt.QShortcut(qt.QKeySequence("Ctrl+e"), slicer.util.mainWindow())
        #shortcut.connect("clicked(bool)", lambda: slicer.ui.radioButton_1.isChecked())
        # Get reference to the radio button widget 
        '''self.radioButton = self.ui.radioButton_1 
            # Create keyboard event handler
        def onKeyPress(event):
            key = event.key()
            if key == QtCore.Qt.Key_1:
                # Check the radio button
                self.radioButton.setChecked(True)
                    
        
        # Connect the keyboard handler 
        shortcut = QtGui.QShortcut(QtGui.QKeySequence("1"), self)
        shortcut.activated.connect(onKeyPress)'''

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        
        self.ui.PathLineEdit = ctk.ctkDirectoryButton()
        
        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.atlasDirectoryButton.directoryChanged.connect(self.onAtlasDirectoryChanged) #if changes, changes as wellloads im folder
        self.ui.save_and_next.connect('clicked(bool)', self.save_and_next_clicked) # saves and goes to next image
        self.ui.overwrite_mask.connect('clicked(bool)', self.overwrite_mask_clicked)    # overwrites the mask with the edited one
        
        # add a paint brush from segment editor window
        # Create a new segment editor widget and add it to the NiftyViewerWidget
        self._createSegmentEditorWidget_()
        
        # Connect new radio button groups
        self.ui.radioButton_1.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_2.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_similar_yes.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_similar_no.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_only_dm.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_only_cm.toggled.connect(self.updateCheckboxVisibility)
        self.ui.radioButton_both_diff.toggled.connect(self.updateCheckboxVisibility)

        # Create button groups for new radio buttons
        self.similarityGroup = qt.QButtonGroup()
        self.similarityGroup.addButton(self.ui.radioButton_similar_yes)
        self.similarityGroup.addButton(self.ui.radioButton_similar_no)
        self.similarityGroup.setExclusive(True)

        self.imageSelectionGroup = qt.QButtonGroup()
        self.imageSelectionGroup.addButton(self.ui.radioButton_only_dm)
        self.imageSelectionGroup.addButton(self.ui.radioButton_only_cm)
        self.imageSelectionGroup.addButton(self.ui.radioButton_both_diff)
        self.imageSelectionGroup.setExclusive(True)
        # --- Both Save buttons trigger the same action ---
        self.ui.save_and_next.clicked.connect(self.save_and_next_clicked)
        self.ui.quick_save_and_next.clicked.connect(self.save_and_next_clicked)

        # --- Keyboard shortcut for both (Ctrl/Command + Return) ---
        save_shortcut = qt.QShortcut(qt.QKeySequence("Ctrl+Return"), self.parent)
        save_shortcut.activated.connect(self.save_and_next_clicked)
        # macOS command key version
        save_shortcut_mac = qt.QShortcut(qt.QKeySequence("Meta+Return"), self.parent)
        save_shortcut_mac.activated.connect(self.save_and_next_clicked)


        # Create real button group for Yes/No
        self.yesNoGroup = qt.QButtonGroup()
        self.yesNoGroup.addButton(self.ui.radioButton_1)
        self.yesNoGroup.addButton(self.ui.radioButton_2)
        self.yesNoGroup.setExclusive(True)


        self.updateCheckboxVisibility()  # initialize multiselect checkboxes
        

        
        #self.segmentEditorWidgetWidget.volumes.collapsed = True
         # Set parameter node first so that the automatic selections made when the scene is set are saved
            
        
        # Make sure parameter node is initialized (needed for module reload)
        #self.initializeParameterNode()


    def _createSegmentEditorWidget_(self): #this parts creates the segmentation bubblw and corresponding features
        """Create and initialize a customize Slicer Editor which contains just some the tools that we need for the segmentation"""

        import qSlicerSegmentationsModuleWidgetsPythonQt

        #advancedCollapsibleButton
        self.segmentEditorWidget = qSlicerSegmentationsModuleWidgetsPythonQt.qMRMLSegmentEditorWidget()
        #enable the "add" button
        #self.segmentEditorWidget.setAddSegmentShortcutEnabled(True)
        
        self.segmentEditorWidget.setMaximumNumberOfUndoStates(10) # 
        self.selectParameterNode()
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        self.segmentEditorWidget.unorderedEffectsVisible = False
        self.segmentEditorWidget.setEffectNameOrder([
            'No editing','Threshold',
            'Paint', 'Draw', 
            'Erase','Level tracing',
            'Grow from seeds','Fill between slices',
            'Margin','Hollow',
            'Smoothing','Scissors',
            'Islands','Logical operators',
            'Mask volume'])
        self.layout.addWidget(self.segmentEditorWidget) 

        # Hide the segmentation editor by default
        self.segmentEditorWidget.setVisible(False)
        # artifact_present = self.ui.radioButton_1.isChecked()
        # self.segmentEditorWidget.setVisible(artifact_present)
        # Observe editor effect registrations to make sure that any effects that are registered
        # later will show up in the segment editor widget. For example, if Segment Editor is set
        # as startup module, additional effects are registered after the segment editor widget is created.
        #self.effectFactorySingleton = slicer.qSlicerSegmentEditorEffectFactory.instance()
        #self.effectFactorySingleton.connect("effectRegistered(QString)", self.editorEffectRegistered)

        # Connect observers to scene events
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)
        
    def enter(self):
        """Runs whenever the module is reopened"""
        #print("Enter")
        
        # Set parameter set node if absent
        self.selectParameterNode()
        self.segmentEditorWidget.updateWidgetFromMRML()

        # If no segmentation node exists then create one so that the user does not have to create one manually
        if not self.segmentEditorWidget.segmentationNodeID():
            #print("No segmentation node, creating one")
            self.segmentation_node = slicer.mrmlScene.GetFirstNode(None, "vtkMRMLSegmentationNode")
            if not self.segmentation_node:
                self.segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            self.segmentEditorWidget.setSegmentationNode(self.segmentation_node)
            if not self.segmentEditorWidget.sourceVolumeNodeID():
                self.sourceVolumeNodeID = self.getDefaultSourceVolumeNodeID()
                self.segmentEditorWidget.setSourceVolumeNodeID(self.sourceVolumeNodeID)
        self.initializeParameterNode()
    
    def updateCheckboxVisibility(self):
        """Control visibility of all artifact selection UI elements based on user selections"""
        artifact_present = self.ui.radioButton_1.isChecked()
        
        # Show similarity question only if artifacts are present
        self.ui.buttongroup_similarity.setVisible(artifact_present)
        
        # Get similarity selection
        similar_artifacts = self.ui.radioButton_similar_yes.isChecked()
        different_artifacts = self.ui.radioButton_similar_no.isChecked()
        
        # Show/hide original artifact group (for similar artifacts on both images)
        self.ui.buttongroup.setVisible(artifact_present and similar_artifacts)
        
        # Show/hide image selection group (only if different artifacts selected)
        self.ui.buttongroup_image_selection.setVisible(artifact_present and different_artifacts)
        
        # Get image selection
        only_dm = self.ui.radioButton_only_dm.isChecked()
        only_cm = self.ui.radioButton_only_cm.isChecked()
        both_diff = self.ui.radioButton_both_diff.isChecked()
        
        # Show/hide DM-specific artifact group
        self.ui.buttongroup_dm.setVisible(artifact_present and different_artifacts and (only_dm or both_diff))
        
        # Show/hide CM-specific artifact group
        self.ui.buttongroup_cm.setVisible(artifact_present and different_artifacts and (only_cm or both_diff))
        
        # Enable/disable checkboxes in original group
        for i in range(1, 8):
            getattr(self.ui, f"checkBox_{i}").setEnabled(artifact_present and similar_artifacts)
        
        # Enable/disable DM checkboxes
        for i in range(1, 8):
            getattr(self.ui, f"checkBox_dm_{i}").setEnabled(artifact_present and different_artifacts and (only_dm or both_diff))
        
        # Enable/disable CM checkboxes
        for i in range(1, 8):
            getattr(self.ui, f"checkBox_cm_{i}").setEnabled(artifact_present and different_artifacts and (only_cm or both_diff))
        
        # Show/hide the segmentation editor widget (only if artifacts present)
        self.segmentEditorWidget.setVisible(artifact_present)
        
        # Show/hide the "Save Outline" button
        self.ui.overwrite_mask.setVisible(artifact_present)
        self.ui.quick_save_and_next.setVisible(self.ui.radioButton_2.isChecked())

    # def overwrite_mask_clicked(self):
    #     # overwrite self.segmentEditorWidget.segmentationNode()
    #     self.segmentation_node = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLSegmentationNode')
    #     file_path = self.joinpath(self.directory,"t.seg.nrrd")
    #     # Save the segmentation node to file as nifti
    #     self.file_path_nifti = str(self.nifti_files[self.current_index]).split(".")[0]+f"_mask_{datetime.now().strftime('%Y%m%d_%H%M%S')}.nii.gz"
    #     self.seg_mask_status[self.current_index] = 3
    #     # add to the list of segmentation files
    #     self.segmentation_files[self.current_index] = self.file_path_nifti
    #     # Save the segmentation node to file
    #     slicer.util.saveNode(self.segmentation_node, file_path)
    #     img = sitk.ReadImage(file_path)
        
    #     sitk.WriteImage(img, self.file_path_nifti)
        
    #     #delete the temporary file
    #     try:
    #         os.remove(file_path)
    #     except:
    #         pass

    def overwrite_mask_clicked(self):
        self.segmentation_node = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLSegmentationNode')
        file_path = os.path.join(self.directory, "t.seg.nrrd")
        
        current_pair = self.image_pairs[self.current_index]
        base_name = current_pair['base_name']
        self.file_path_nifti = os.path.join(
            self.directory, 
            f"{base_name}_mask_{datetime.now().strftime('%Y%m%d_%H%M%S')}.nii.gz"
        )
        
        slicer.util.saveNode(self.segmentation_node, file_path)
        img = sitk.ReadImage(file_path)
        sitk.WriteImage(img, self.file_path_nifti)
        
        try:
            os.remove(file_path)
        except:
            pass


    
    def joinpath(self, rootdir, filename):
        return os.path.join(rootdir, filename)
        
    def _construct_full_path(self, path):
        if os.path.isabs(path):
            return path
        else:
            return self.joinpath(self.directory, path)

    def _is_valid_extension(self, path):
        # First check normal image extensions
        valid_ext = [".nii", ".nii.gz", ".nrrd", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".dcm"]
        lower = path.lower()

        if any(lower.endswith(ext) for ext in valid_ext):
            return True

        # --- Now detect DICOM files with no extension ---
        try:
            with open(path, "rb") as f:
                f.seek(128)
                is_dicom = f.read(4) == b"DICM"
            return is_dicom
        except:
            return False

    def _parse_filename(self, filename):
        """
        Parse filename like P1_L_DM_CC.jpg or P1_R_CM_MLO.jpg
        Returns dict with patient, laterality, image_type, view
        """
        pattern = r'P(\d+)_([LR])_(DM|CM)_(CC|MLO)'
        match = re.match(pattern, filename, re.IGNORECASE)
        
        if match:
            return {
                'patient': match.group(1),
                'laterality': match.group(2).upper(),
                'image_type': match.group(3).upper(),
                'view': match.group(4).upper(),
                'filename': filename
            }
        return None
    
    def _group_image_pairs(self, files):
        """
        Group DM and CM images into pairs based on patient, laterality, and view.
        Returns list of dicts with 'DM' and 'CM' file paths.
        """
        parsed_files = []
        for f in files:
            parsed = self._parse_filename(os.path.basename(f))
            if parsed:
                parsed['full_path'] = f
                parsed_files.append(parsed)
        
        # Group by patient_laterality_view
        pairs_dict = {}
        for pf in parsed_files:
            key = f"P{pf['patient']}_{pf['laterality']}_{pf['view']}"
            if key not in pairs_dict:
                pairs_dict[key] = {'base_name': key, 'patient': pf['patient'], 
                                   'laterality': pf['laterality'], 'view': pf['view']}
            
            pairs_dict[key][pf['image_type']] = pf['full_path']
        
        # Only keep complete pairs (both DM and CM)
        complete_pairs = []
        for key, pair_info in pairs_dict.items():
            if 'DM' in pair_info and 'CM' in pair_info:
                complete_pairs.append(pair_info)
        
        # Sort by patient number, laterality, then view
        complete_pairs.sort(key=lambda x: (int(x['patient']), x['laterality'], x['view']))
        
        return complete_pairs
    


    
    def _restore_index(self, ann_csv, files_list, mask_list, mask_status_list=None):
        #print(files_list,mask_list)
        #print(self.unique_case_flag)
        #ann_csv {[self.nifti_files[self.current_index]],[likert_score],[self.ui.comment.toPlainText()]}
        statuses, unchecked_files, unchecked_masks, checked_ids, id_subs_list = [], [], [], [], []
        list_of_checked = ann_csv['file'].values
        list_of_checked = [self._construct_full_path(i) for i in list_of_checked]
        
        list_of_checked_masks = ann_csv['mask_path'].values
        #print(list_of_checked)
        # check if ['mask_path'] is empty
        if type(list_of_checked_masks[0]) == str:
            list_of_checked_masks = [self._construct_full_path(i) for i in list_of_checked_masks]
        
        #find subset of files that are not checked
        if self.unique_case_flag:
            # read what ids were checked by finding the corresponding ids
            checked_ids = []
            list_of_checked = ann_csv['file'].values
            # first, check what ids were checked
            for id_subj, img, _ in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                if img in list_of_checked:
                    checked_ids.append(id_subj)
            # second, find the files that were not checked       
            for id_subj, img, mask in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                if id_subj not in checked_ids:
                    id_subs_list.append(id_subj)
                    unchecked_files.append(self._construct_full_path(img))
                    # check if mask is empty or nan 
                    if type(mask) == str:
                        unchecked_masks.append(self._construct_full_path(mask))
                        statuses.append(2)
                    else:
                        unchecked_masks.append("")
                        statuses.append(0)
                        
            #print("Checked ids",checked_ids)
            #print("Unchecked files",unchecked_files)
            #print("Unchecked masks",unchecked_masks)
            
        else:
            for i in range(len(files_list)):
                if files_list[i] not in list_of_checked:
                    unchecked_files.append(files_list[i])
                    unchecked_masks.append(mask_list[i])
                    statuses.append(mask_status_list[i])
        
        
        #return list of unchecked files
        return unchecked_files, unchecked_masks, statuses, id_subs_list, checked_ids
    
    def getDefaultSourceVolumeNodeID(self):
        layoutManager = slicer.app.layoutManager()
        firstForegroundVolumeID = None
        # Use first background volume node in any of the displayed layouts.
        # If no beackground volume node is in any slice view then use the first
        # foreground volume node.
        for sliceViewName in layoutManager.sliceViewNames():
            sliceWidget = layoutManager.sliceWidget(sliceViewName)
            if not sliceWidget:
                continue
            compositeNode = sliceWidget.mrmlSliceCompositeNode()
            if compositeNode.GetBackgroundVolumeID():
                return compositeNode.GetBackgroundVolumeID()
            if compositeNode.GetForegroundVolumeID() and not firstForegroundVolumeID:
                firstForegroundVolumeID = compositeNode.GetForegroundVolumeID()
        # No background volume was found, so use the foreground volume (if any was found)
        return firstForegroundVolumeID 
   
    def editorEffectRegistered(self):
        self.segmentEditorWidget.updateEffectList()
        
    def selectParameterNode(self):
        # Select parameter set node if one is found in the scene, and create one otherwise
        segmentEditorSingletonTag = "SegmentEditor"
        segmentEditorNode = slicer.mrmlScene.GetSingletonNode(segmentEditorSingletonTag, "vtkMRMLSegmentEditorNode")
        if segmentEditorNode is None:
            segmentEditorNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentEditorNode")
            segmentEditorNode.UnRegister(None)
            segmentEditorNode.SetSingletonTag(segmentEditorSingletonTag)
            segmentEditorNode = slicer.mrmlScene.AddNode(segmentEditorNode)
        #if self.parameterSetNode == segmentEditorNode:
        #    # nothing changed
        #    return
        self.parameterSetNode = segmentEditorNode
        self.segmentEditorWidget.setMRMLSegmentEditorNode(self.parameterSetNode)
   
    def onAtlasDirectoryChanged(self, directory):
        """these parts have the be changes since now autmatic masks are mtacthed with their nifitt, mine do not have segmentations yet (maybe some already do ifi in process)
        also 2d data, how is this handeled differently , does it need ot be handled in """
        
        self.directory = os.path.normpath(directory)
        directory = self.directory
        logger = logging.getLogger('CEMArtifacts')
        logger.setLevel(logging.DEBUG)

        # Set up logging to file
        fileHandler = logging.FileHandler(self.joinpath(directory,'cem_artifacts.log'))
        fileHandler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(fileHandler) 
        
        try:
            # Clear existing volumes
            for pair in self.volume_pairs.values():
                for vol in pair.values():
                    if vol:
                        slicer.mrmlScene.RemoveNode(vol)
            self.volume_pairs = {}
            
            if self.segmentation_node:
                slicer.mrmlScene.RemoveNode(self.segmentation_node)
        except:
            pass
        
        # self.unique_case_flag=False

        mapping_unique = os.path.join(directory, "mapping_unique.csv")
        mapping_file = os.path.join(directory, "mapping.csv")
        # case 0: searching for one unique nifti file for id
        # they 




        if os.path.isfile(mapping_unique):
            case_flag = True
            # mapping file contains id and nifti file name
            id_subs = []
            self.mappings = pd.read_csv(self.joinpath(directory,"mapping_unique.csv"))
            self.unique_case_flag = True
            for id_subj, img, mask in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                # counting images
                if os.path.exists(self.joinpath(directory,img)) and self._is_valid_extension(self.joinpath(directory,img)):
                    self.nifti_files.append(self.joinpath(directory,img))
                    id_subs.append(id_subj)
                    # counting masks
                    # check if mask is 
                    if type(mask) == str:
                        if os.path.exists(self.joinpath(directory,mask)) and self._is_valid_extension(self.joinpath(directory,mask)):
                            
                            self.segmentation_files.append(self.joinpath(directory,mask))
                            self.seg_mask_status.append(2) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'Found mask for {img}')
                        elif self._is_valid_extension(self.joinpath(directory,mask)) and not os.path.exists(self.joinpath(directory,mask)):
                           
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(1) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'Cannot load mask for {img}, check path')
                        else:
                            
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(0) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'No mask provided for {img}')
                    else:
                        
                        self.segmentation_files.append("")
                        self.seg_mask_status.append(0)
                        logger.info(f'No mask provided for {img}')
                else:
                    logger.info(f'File {img} does not exist or has wrong extension, skipping')
            #get unique ids
            self.id_subs = id_subs
            #print("Unique:",len(np.unique(self.id_subs)),id_subs)   
        
        # case 1: mapper cvs is present
        elif os.path.isfile(mapping_file):
            logger.info('Found mappings between files and masks') 
            #print("Found mappings between files and masks")
            self.mappings = pd.read_csv(self.joinpath(directory,"mapping.csv"))
            self.with_mapper_flag = True
            # casting to zero all nan values
            
            #print("Loaded mappings between files and masks")
            for img, mask in zip(self.mappings["img_path"], self.mappings["mask_path"]):
                # counting images
                if os.path.exists(self.joinpath(directory,img)) and self._is_valid_extension(self.joinpath(directory,img)):
                    self.nifti_files.append(self.joinpath(directory,img))
                    # counting masks
                    # check if mask is 
                    if type(mask) == str:
                        if os.path.exists(self.joinpath(directory,mask)) and self._is_valid_extension(self.joinpath(directory,mask)):
                            self.segmentation_files.append(self.joinpath(directory,mask))
                            self.seg_mask_status.append(2) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'Found mask for {img}')
                        elif self._is_valid_extension(self.joinpath(directory,mask)) and not os.path.exists(self.joinpath(directory,mask)):
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(1) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'Cannot load mask for {img}, check path')
                        else:
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(0) # 0 - no mask, 1 - mask path, cannot load , 2 - mask loaded
                            logger.info(f'No mask provided for {img}')
                    else:
                        self.segmentation_files.append("")
                        self.seg_mask_status.append(0)
                        logger.info(f'No mask provided for {img}')
                else:
                    logger.info(f'File {img} does not exist or has wrong extension, skipping')                   
                # ToDo: write to log how many files were found, how many masks were found 
                
                
    
        # case 2: no mapper found → detect images + DICOM
        else:
            logger.info('No mappings between files and masks')
            # processed_files = set()


            valid_files = []
            for file in os.listdir(directory):
                full_path = os.path.join(directory, file)
                if os.path.isfile(full_path) and file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    if '_mask' not in file.lower():
                        valid_files.append(full_path)
            


                base = os.path.splitext(file)[0]

                possible_masks = [
                    os.path.join(directory, base + "_mask.nrrd"),
                    os.path.join(directory, base + "_mask.nii.gz"),
                    os.path.join(directory, base + "_mask.nii"),
                ]

                mask_found = next((m for m in possible_masks if os.path.exists(m)), None)

                if mask_found:
                    self.segmentation_files.append(mask_found)
                    self.seg_mask_status.append(2)
                    logger.info(f"Found mask for {file}")
                else:
                    self.segmentation_files.append("")
                    self.seg_mask_status.append(0)
                    logger.info(f"No mask for {file}")


        # Group into DM/CM pairs
        self.image_pairs = self._group_image_pairs(valid_files)
        print(self.image_pairs)
        self.n_pairs = len(self.image_pairs)
        
        logger.info(f'Found {self.n_pairs} complete DM/CM pairs')
        
        self.current_index = 0         
        # load the .cvs file with the old annotations or create a new one
        #print("Path exists",os.path.exists(self.joinpath(directory,"annotations.csv")))
        # Check for existing annotations
        ann_path = os.path.join(directory, "annotations.csv")
        if os.path.exists(ann_path):
            ann_csv = pd.read_csv(ann_path, header=None, index_col=False,
                                 names=["base_name", "artifact_type", "dm_artifacts","cm_artifacts", "other", "mask_path", "mask_status"])
            
            completed_bases = set(ann_csv['base_name'].values)
            self.image_pairs = [p for p in self.image_pairs if p['base_name'] not in completed_bases]
            self.n_pairs = len(self.image_pairs)
            logger.info(f'Restored session: {self.n_pairs} pairs remaining')
        
    
        self.ui.status_checked.setText(f"Checked: {self.current_index} / {self.n_pairs}")
        
        if self.n_pairs > 0:
            print("shoudlnow load new im pair")
            self.load_image_pair()

     # ______________________________________________________________________________________________________________________________________ ___________________________________________________________________ 

# 

    
    def setupSideBySideLayout(self, dm_volume, cm_volume):
        """Setup the side-by-side layout with DM on left, CM on right using built-in Slicer layout"""
        # Use built-in side-by-side layout
        lm = slicer.app.layoutManager()
        lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)
        
        def views_ready():
            # In the built-in side-by-side layout, views are named "Red" and "Yellow"
            return lm.sliceWidget("Red") is not None and lm.sliceWidget("Yellow") is not None
        
        def wire_volumes():
            # Red view (left) = DM, Yellow view (right) = CM
            for tag, vol in [("Red", dm_volume), ("Yellow", cm_volume)]:
                sw = lm.sliceWidget(tag)
                if not sw:
                    continue
                    
                logic = sw.sliceLogic()
                comp = logic.GetSliceCompositeNode()
                sn = logic.GetSliceNode()
                
                # Set the background volume
                comp.SetBackgroundVolumeID(vol.GetID())
                comp.SetForegroundVolumeID(None)
                comp.SetLabelVolumeID(None)
                
                # Disable foreground opacity (removes color overlay)
                comp.SetForegroundOpacity(0.0)
                
                # Force axial orientation (also known as transverse/horizontal)
                sn.SetOrientationToAxial()
                sn.UpdateMatrices()
                
                # Reset the slice viewer to grayscale (remove Red/Yellow tint)
                displayNode = vol.GetDisplayNode()
                if displayNode:
                    displayNode.SetAndObserveColorNodeID("vtkMRMLColorTableNodeGrey")
                
                # Fit the view to the image
                logic.FitSliceToAll()
                
                # Apply a slight zoom
                fov = sn.GetFieldOfView()
                sn.SetFieldOfView(fov[0]*0.88, fov[1]*0.88, fov[2])
        
        def poll():
            if views_ready():
                wire_volumes()
            else:
                qt.QTimer.singleShot(50, poll)
        
        qt.QTimer.singleShot(0, poll)


    def load_image_pair(self):
        """Load a pair of DM and CM images side by side"""
        print(f"[DEBUG] load_image_pair called - _is_loading={self._is_loading}, index={self.current_index}")
        
        if self._is_loading:
            print(f"[DEBUG] Already loading, skipping load_image_pair")
            return
        self._is_loading = True
        
        try:
            if self.current_index >= self.n_pairs:
                print(f"[DEBUG] Index {self.current_index} >= n_pairs {self.n_pairs}, showing completion message")
                qt.QMessageBox.information(
                    slicer.util.mainWindow(), 
                    "Complete", 
                    "All image pairs have been reviewed!"
                )
                self._is_loading = False
                return
            
            logger = logging.getLogger('CEMArtifacts')
            current_pair = self.image_pairs[self.current_index]
            
            print(f"[DEBUG] Loading pair: {current_pair['base_name']}")
            print(f"[DEBUG] DM: {current_pair['DM']}")
            print(f"[DEBUG] CM: {current_pair['CM']}")
            
            # Clean up previous volumes
            slicer.app.layoutManager().setRenderPaused(True)
            
            try:
                if hasattr(self, 'segmentEditorWidget'):
                    self.segmentEditorWidget.setSegmentationNode(None)
                    self.segmentEditorWidget.setSourceVolumeNode(None)
                
                for pair in self.volume_pairs.values():
                    for node in pair.values():
                        if node and slicer.mrmlScene.IsNodePresent(node):
                            slicer.mrmlScene.RemoveNode(node)
                
                self.volume_pairs = {}


                if self.segmentation_node and slicer.mrmlScene.IsNodePresent(self.segmentation_node):
                    slicer.mrmlScene.RemoveNode(self.segmentation_node)
                self.segmentation_node = None
                
                slicer.app.processEvents()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            
            slicer.util.resetSliceViews()

            # Load DM and CM images
            dm_path = current_pair['DM']
            cm_path = current_pair['CM']
            
            readerFactory = vtk.vtkImageReader2Factory()
            
            # Load DM image
            print(f"[DEBUG] Loading DM image...")
            dm_reader = readerFactory.CreateImageReader2(dm_path)
            if dm_reader:
                dm_reader.SetFileName(dm_path)
                dm_reader.Update()
                
                dm_volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLVectorVolumeNode")
                dm_volume.SetName(f"{current_pair['base_name']}_DM")
                dm_volume.SetAndObserveImageData(dm_reader.GetOutput())
                dm_volume.SetSpacing(1, 1, 1)
                print(f"[DEBUG] DM volume loaded: {dm_volume.GetName()}")
            else:
                raise Exception(f"Could not load DM image: {dm_path}")
        
            # Load CM image
            print(f"[DEBUG] Loading CM image...")
            cm_reader = readerFactory.CreateImageReader2(cm_path)
            if cm_reader:
                cm_reader.SetFileName(cm_path)
                cm_reader.Update()
                
                cm_volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLVectorVolumeNode")
                cm_volume.SetName(f"{current_pair['base_name']}_CM")
                cm_volume.SetAndObserveImageData(cm_reader.GetOutput())
                cm_volume.SetSpacing(1, 1, 1)
                print(f"[DEBUG] CM volume loaded: {cm_volume.GetName()}")
            else:
                raise Exception(f"Could not load CM image: {cm_path}")
            # # ----- LOAD DM -----
            # dm_reader = vtk.vtkJPEGReader()
            # dm_reader.SetFileName(current_pair['DM']); dm_reader.Update()
            # dm_volume = slicer.modules.volumes.logic().CreateVolume(dm_reader.GetOutput())
            # dm_volume.SetName(f"{current_pair['base_name']}_DM")

            # # ----- LOAD CM -----
            # cm_reader = vtk.vtkJPEGReader()
            # cm_reader.SetFileName(current_pair['CM']); cm_reader.Update()
            # cm_volume = slicer.modules.volumes.logic().CreateVolume(cm_reader.GetOutput())
            # cm_volume.SetName(f"{current_pair['base_name']}_CM")

            # Store volume pair
            self.volume_pairs[current_pair['base_name']] = {
                'DM': dm_volume,
                'CM': cm_volume
            }

            print(f"[DEBUG] Setting up side-by-side layout...")
            
            # Setup side-by-side layout
            self.setupSideBySideLayout(dm_volume, cm_volume)

            print(f"[DEBUG] Layout setup complete")
            
            logger.info(f"Loaded pair: {current_pair['base_name']}")
            
            # Resume rendering
            slicer.app.layoutManager().setRenderPaused(False)
            slicer.app.processEvents()
            
            print(f"[DEBUG] load_image_pair completed successfully")
            self._is_loading = False
            return 1
            
        except Exception as e:
            logger = logging.getLogger('CEMArtifacts')
            logger.error(f"Failed to load image pair: {e}")
            print(f"[DEBUG] ERROR in load_image_pair: {e}")
            import traceback
            traceback.print_exc()
            qt.QMessageBox.critical(
                slicer.util.mainWindow(),
                "Load Error",
                f"Could not load image pair\nError: {str(e)}"
            )
            slicer.app.layoutManager().setRenderPaused(False)
            self._is_loading = False
            return 0
        
        finally:
            self._is_loading = False

    def _numerical_status_to_str(self, status):
        return {0: "No mask found", 1: "Cannot load mask", 2: "Mask loaded, no edits", 3:"Mask edited"}[status]   
    
    def _artifacts_to_str(self, artifact_ids):
        mapping = {
            1: "Breast in Breast",
            2: "Skin Illumination",
            3: "Air Trapping",
            4: "Ripple (Motion Artifact)",
            5: "Contrast Splatter",
            6: "Implant",
            7: "Other"
        }
        return ", ".join([mapping[i] for i in artifact_ids])
    #DO these have to be ina ccordance iwht button from .ui? ie or is labels for csv files?
# ______________________________________________________________________________________________________________________________________ ___________________________________________________________________ 

    # def save_and_next_clicked(self):

    #     # # Prevent re-entry (double clicks, UI event glitches)
    #     # if self._is_loading:
    #     #     return
    #     # self._is_loading = True

    #     try:
            
    #         # 1. Detect artifact state
    #         artifact_present = None
    #         if self.ui.radioButton_1.isChecked():  # Yes
    #             artifact_present = True
    #         elif self.ui.radioButton_2.isChecked():  # No
    #             artifact_present = False

    #         if artifact_present is None:
    #             # slicer.util.errorDisplay("Please select Yes or No before continuing.")
    #             return
            
    #         # 2. Build annotation string
            
    #         if not artifact_present:
    #             annotation = "No artifact"
    #             artifact_list = []
    #         else:
    #             artifact_list = []
    #             for i in range(1, 8):
    #                 checkbox = getattr(self.ui, f"checkBox_{i}")
    #                 if checkbox.isChecked():
    #                     artifact_list.append(i)

    #             if not artifact_list:
    #                 slicer.util.warningDisplay(
    #                     "You selected 'Yes' but no artifact type — please choose at least one."
    #                 )
    #                 return

    #             annotation = self._artifacts_to_str(artifact_list)

            
    #         # 3. Save comment
    #         comment_text = self.ui.comment.toPlainText()
    #         current_pair = self.image_pairs[self.current_index]
    #         # self.likert_scores.append([self.current_index, annotation, comment_text])

            
    #         # 4. Append to CSV
    #         # head, tail = os.path.split(self.nifti_files[self.current_index])
    #         # data = {
    #         #     'file': [self.nifti_files[self.current_index].replace(head, "").replace("/", "").replace("\\", "")],
    #         #     'artifacts': [annotation],
    #         #     'other': [comment_text],
    #         #     'mask_path': [self.segmentation_files[self.current_index].replace(head, "").replace("/", "").replace("\\", "")],
    #         #     'mask_status': [self._numerical_status_to_str(self.seg_mask_status[self.current_index])]
    #         # }
    #         data = {
    #             'base_name': [current_pair['base_name']],
    #             'artifacts': [annotation],
    #             'other': [comment_text],
    #             'mask_path': [""],
    #             'mask_status': ["No mask"]
    #         }

    #         df = pd.DataFrame(data)
    #         df.to_csv(self.joinpath(self.directory, "annotations.csv"),
    #                 mode='a', index=False, header=False)

            
    #         # # 5. Store window/level + visibility state
    #         # if self.volume_node and self.volume_node.GetDisplayNode():
    #         #     self.store_current_window_level_settings()

    #         # if self.segmentation_node:
    #         #     self.store_segment_visiblity_states()

            
    #         # # 6. COMPUTE NEXT INDEX SAFELY
    #         # if self.current_index >= self.n_files - 1:
    #         #     print("All files checked")
    #         #     self.finish_flag = True
    #         #     return

    #         # # Unique mode → skip already checked subjects -pa
    #         # if self.unique_case_flag:
    #         #     next_index = self.current_index + 1

    #         #     while (
    #         #         next_index < self.n_files
    #         #         and self.id_subs[next_index] in self.id_subs_checked
    #         #     ):
    #         #         next_index += 1

    #         #     if next_index >= self.n_files:
    #         #         print("All files checked")
    #         #         self.finish_flag = True
    #         #         return

    #         #     self.current_index = next_index

    #         # # Normal mode
    #         # else:
    #         #     self.current_index += 1

            
    #         # 7. RESET UI BEFORE LOADING NEXT IMAGE
    #         # reset artifacts
    #         for i in range(1, 8):
    #             getattr(self.ui, f"checkBox_{i}").setChecked(False)
                
    #         ## Reset Yes/No radio buttons safely
    #         self.yesNoGroup.setExclusive(False)
    #         self.ui.radioButton_1.setChecked(False)
    #         self.ui.radioButton_2.setChecked(False)
    #         self.ui.comment.clear()
    #         slicer.app.processEvents()
    #         self.yesNoGroup.setExclusive(True)
    #         slicer.app.processEvents()
            
    #         print("idx & pairs:",self.current_index, self.n_pairs)
    #         # Move to next pair
    #         if self.current_index >= self.n_pairs - 1:
                
    #             print("All pairs checked")
    #             return
    #         else:
    #             self.current_index += 1
    #             self.load_image_pair()
            
    #         self.ui.status_checked.setText(
    #             f"Checked: {self.current_index} / {self.n_pairs}"
    #         )
    #         # # 8. LOAD NEXT IMAGE EXACTLY ONCE
    #         # if self.unique_case_flag:
    #         #     self.load_image_file(unique=True)
    #         # else:
    #         #     self.load_image_file(unique=False)

            

    #     finally:
    #         # Ensure unlock even if an exception happens
    #         self._is_loading = False


    def save_and_next_clicked(self):
        try:
            # 1. Detect artifact state
            artifact_present = None
            if self.ui.radioButton_1.isChecked():
                artifact_present = True
            elif self.ui.radioButton_2.isChecked():
                artifact_present = False

            if artifact_present is None:
                return
            
            # 2. Build annotation strings for DM and CM
            dm_annotation = "No artifact"
            cm_annotation = "No artifact"
            artifact_type = "none"
            
            if not artifact_present:
                dm_annotation = "No artifact"
                cm_annotation = "No artifact"
                artifact_type = "none"
            else:
                # Check if similar or different artifacts
                similar_artifacts = self.ui.radioButton_similar_yes.isChecked()
                different_artifacts = self.ui.radioButton_similar_no.isChecked()
                
                if not similar_artifacts and not different_artifacts:
                    slicer.util.warningDisplay("Please specify if artifacts are similar or different between DM and CM.")
                    return
                
                if similar_artifacts:
                    # Use original checkboxes - same artifacts on both images
                    artifact_list = []
                    for i in range(1, 8):
                        checkbox = getattr(self.ui, f"checkBox_{i}")
                        if checkbox.isChecked():
                            artifact_list.append(i)
                    
                    if not artifact_list:
                        slicer.util.warningDisplay("You selected 'Yes' but no artifact type – please choose at least one.")
                        return
                    
                    annotation_str = self._artifacts_to_str(artifact_list)
                    dm_annotation = annotation_str
                    cm_annotation = annotation_str
                    artifact_type = "similar"
                    
                elif different_artifacts:
                    # Check which image(s) have artifacts
                    only_dm = self.ui.radioButton_only_dm.isChecked()
                    only_cm = self.ui.radioButton_only_cm.isChecked()
                    both_diff = self.ui.radioButton_both_diff.isChecked()
                    
                    if not (only_dm or only_cm or both_diff):
                        slicer.util.warningDisplay("Please specify which image(s) contain artifacts.")
                        return
                    
                    if only_dm:
                        # Check DM checkboxes
                        dm_artifact_list = []
                        for i in range(1, 8):
                            checkbox = getattr(self.ui, f"checkBox_dm_{i}")
                            if checkbox.isChecked():
                                dm_artifact_list.append(i)
                        
                        if not dm_artifact_list:
                            slicer.util.warningDisplay("Please select at least one artifact type for DM.")
                            return
                        
                        dm_annotation = self._artifacts_to_str(dm_artifact_list)
                        cm_annotation = "No artifact"
                        artifact_type = "only_dm"
                        
                    elif only_cm:
                        # Check CM checkboxes
                        cm_artifact_list = []
                        for i in range(1, 8):
                            checkbox = getattr(self.ui, f"checkBox_cm_{i}")
                            if checkbox.isChecked():
                                cm_artifact_list.append(i)
                        
                        if not cm_artifact_list:
                            slicer.util.warningDisplay("Please select at least one artifact type for CM.")
                            return
                        
                        dm_annotation = "No artifact"
                        cm_annotation = self._artifacts_to_str(cm_artifact_list)
                        artifact_type = "only_cm"
                        
                    elif both_diff:
                        # Check both DM and CM checkboxes
                        dm_artifact_list = []
                        for i in range(1, 8):
                            checkbox = getattr(self.ui, f"checkBox_dm_{i}")
                            if checkbox.isChecked():
                                dm_artifact_list.append(i)
                        
                        cm_artifact_list = []
                        for i in range(1, 8):
                            checkbox = getattr(self.ui, f"checkBox_cm_{i}")
                            if checkbox.isChecked():
                                cm_artifact_list.append(i)
                        
                        if not dm_artifact_list or not cm_artifact_list:
                            slicer.util.warningDisplay("Please select at least one artifact type for both DM and CM.")
                            return
                        
                        dm_annotation = self._artifacts_to_str(dm_artifact_list)
                        cm_annotation = self._artifacts_to_str(cm_artifact_list)
                        artifact_type = "both_different"
            
            # 3. Save comment
            comment_text = self.ui.comment.toPlainText()
            current_pair = self.image_pairs[self.current_index]
            
            # 4. Append to CSV with separate DM and CM columns
            data = {
                'base_name': [current_pair['base_name']],
                'artifact_type': [artifact_type],
                'dm_artifacts': [dm_annotation],
                'cm_artifacts': [cm_annotation],
                'other': [comment_text],
                'mask_path': [""],
                'mask_status': ["No mask"]
            }

            df = pd.DataFrame(data)
            df.to_csv(self.joinpath(self.directory, "annotations.csv"),
                    mode='a', index=False, header=False)
            
            # 5. RESET UI BEFORE LOADING NEXT IMAGE
            # Reset original artifact checkboxes
            for i in range(1, 8):
                getattr(self.ui, f"checkBox_{i}").setChecked(False)
            
            # Reset DM artifact checkboxes
            for i in range(1, 8):
                getattr(self.ui, f"checkBox_dm_{i}").setChecked(False)
            
            # Reset CM artifact checkboxes
            for i in range(1, 8):
                getattr(self.ui, f"checkBox_cm_{i}").setChecked(False)
            
            # Reset all radio button groups
            self.yesNoGroup.setExclusive(False)
            self.ui.radioButton_1.setChecked(False)
            self.ui.radioButton_2.setChecked(False)
            self.yesNoGroup.setExclusive(True)
            
            self.similarityGroup.setExclusive(False)
            self.ui.radioButton_similar_yes.setChecked(False)
            self.ui.radioButton_similar_no.setChecked(False)
            self.similarityGroup.setExclusive(True)
            
            self.imageSelectionGroup.setExclusive(False)
            self.ui.radioButton_only_dm.setChecked(False)
            self.ui.radioButton_only_cm.setChecked(False)
            self.ui.radioButton_both_diff.setChecked(False)
            self.imageSelectionGroup.setExclusive(True)
            
            self.ui.comment.clear()
            slicer.app.processEvents()
            
            # Move to next pair
            if self.current_index >= self.n_pairs - 1:
                print("All pairs checked")
                qt.QMessageBox.information(
                    slicer.util.mainWindow(),
                    "Complete",
                    "All image pairs have been reviewed!"
                )
                return
            else:
                self.current_index += 1
                self.load_image_pair()
            
            self.ui.status_checked.setText(
                f"Checked: {self.current_index} / {self.n_pairs}"
            )

        finally:
            self._is_loading = False

    def store_current_window_level_settings(self):
        """Store current HU window and level settings."""
        self.window_level = (self.volume_node.GetDisplayNode().GetWindow(), self.volume_node.GetDisplayNode().GetLevel())

    def restore_window_level_settings(self):
        if not self.volume_node: #added this as recommendation
            return

        if not self.volume_node.GetDisplayNode(): #added this as recommendation
            return
        
        if self.window_level is not None:
            self.volume_node.GetDisplayNode().SetAutoWindowLevel(False)
            self.volume_node.GetDisplayNode().SetWindow(self.window_level[0])
            self.volume_node.GetDisplayNode().SetLevel(self.window_level[1])
        else:
            self.volume_node.GetDisplayNode().SetAutoWindowLevel(True)

    def store_segment_visiblity_states(self):
        """Store the visibility states of mask labels."""
        for segment_id in self.segmentation_node.GetSegmentation().GetSegmentIDs():
            visibility = self.segmentation_node.GetDisplayNode().GetSegmentVisibility(segment_id)
            self.segment_visiblity_states[segment_id] = visibility

    def restore_segment_visiblity_states(self):
        """Restore the visibility states of mask labels.""" 
        for segment_id in self.segmentation_node.GetSegmentation().GetSegmentIDs():
            visibility = self.segment_visiblity_states.get(segment_id, True)
            self.segmentation_node.GetDisplayNode().SetSegmentVisibility(segment_id, visibility)


    def set_segmentation_and_mask_for_segmentation_editor(self):
        slicer.app.processEvents()
        
        # Set up segment editor widget
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        self.segmentEditorWidget.setMRMLSegmentEditorNode(slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode"))
        self.segmentEditorWidget.setSegmentationNode(self.segmentation_node)
        self.segmentEditorWidget.setSourceVolumeNode(self.volume_node)
        
        # Compute centroids and jump to them
        segStatLogic = SegmentStatistics.SegmentStatisticsLogic()
        segStatLogic.getParameterNode().SetParameter("Segmentation", self.segmentation_node.GetID())
        segStatLogic.getParameterNode().SetParameter("LabelmapSegmentStatisticsPlugin.centroid_ras.enabled", str(True))
        segStatLogic.computeStatistics()
        stats = segStatLogic.getStatistics()
        
        self.pointListNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode")
        self.pointListNode.CreateDefaultDisplayNodes()
        
        markupsLogic = slicer.modules.markups.logic()
        for segmentId in stats["SegmentIDs"]:
            if self.segment_visiblity_states.get(segmentId, True):
                centroid_ras = stats[segmentId, "LabelmapSegmentStatisticsPlugin.centroid_ras"]
                markupsLogic.JumpSlicesToLocation(*centroid_ras, False)

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()
        #self.effectFactorySingleton.disconnect("effectRegistered(QString)", self.editorEffectRegistered)

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        try:
            self.setParameterNode(None)
            self.segmentEditorWidget.setSegmentationNode(None)
            self.segmentEditorWidget.removeViewObservations()
        except:
            pass

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()
            self.selectParameterNode()
            self.segmentEditorWidget.updateWidgetFromMRML()  
        
    def onSceneEndImport(self, caller, event):
        if self.parent.isEntered:
            self.selectParameterNode()
            self.segmentEditorWidget.updateWidgetFromMRML()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.GetNodeReference("InputVolume"):
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """
        #if inputParameterNode:
        #    self.logic.setDefaultParameters(inputParameterNode)
        
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True
        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

        self._parameterNode.EndModify(wasModified)
# SlicerLikertDLratingLogic
#

class SlicerLikertDLratingLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    
#
# SlicerLikertDLratingTest
#

class SlicerLikertDLratingTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_SlicerLikertDLrating1()

    def test_SlicerLikertDLrating1(self):
 

        self.delayDisplay("Starting the test")

        self.delayDisplay('Test passed')

# At the very end of CEMArtifacts.py, add:
if __name__ == "__main__":
    import sys
    
    # Instantiate and show the module widget
    parent = slicer.qMRMLWidget()
    parent.show()
    widget = CEMArtifactsWidget(parent)
    widget.setup()