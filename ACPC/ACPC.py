import logging
import os
from typing import Annotated, Optional, Any

import vtk

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode
import numpy as np

#
# ACPC
#


class ACPC(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("ACPC")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Brain Implant Wizard")]
        self.parent.dependencies = []
        self.parent.contributors = ["Arjun R Khanna, MD (UCSD Neurosurgery)"]
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
A module to calculate an AC-PC transformation based on a user-specified AC-PC line and a midline point.
                                 For use in planning electrode trajectories.
                                 For research use only. Not for clinical use.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was developed by Arjun R Khanna, MD at UC-San Diego.
""")

        # Additional initialization step after application startup is complete
        #slicer.app.connect("startupCompleted()", registerSampleData)


#
# ACPCParameterNode
#


# @parameterNodeWrapper
# class ACPCParameterNode:
#     """
#     The parameters needed by module.

#     targetingVolume - The volume to transform.
#     acpcLine - A line that goes from the anterior commissure to the posterior commissure.
#     midlinePoint - A midline point(s)
#     """
#     targetingVolume: vtkMRMLScalarVolumeNode
#     acpcLine: vtkMRMLMarkupsLineNode
#     # midlinePoint: vtkMRMLScalarVolumeNode


#
# ACPCWidget
#


class ACPCWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

        # Initialize observers that run the processing algorithm when specific parameters are changed
        self.acpc_observer = None
        self.midpoint_observer = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/ACPC.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = ACPCLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)
        self.ui.select_realTimeUpdate.connect("stateChanged(int)", self.onCheckboxStateChanged)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()
        if self.acpc_observer is not None:
            self.ui.select_acpcLine.currentNode().RemoveObserver(self.acpc_observer)
            self.acpc_observer = None
        if self.midpoint_observer is not None:
            self.ui.select_midlinePoints.currentNode().RemoveObserver(self.midpoint_observer)
            self.midpoint_observer = None

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._updateButtonStates)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.acpcLine:
            firstLineNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLMarkupsLineNode")
            if firstLineNode:
                self._parameterNode.acpcLine = firstLineNode

        if not self._parameterNode.midlinePoints:
            firstFiducialNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLMarkupsFiducialNode")
            if firstFiducialNode:
                self._parameterNode.midlinePoints = firstFiducialNode

    def setParameterNode(self, inputParameterNode) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._updateButtonStates)

        self._parameterNode = inputParameterNode

        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._updateButtonStates)
            self._updateButtonStates()

    def _updateButtonStates(self, caller=None, event=None) -> None:
        # Enable apply and realTimeUpdate buttons depending on the state of the parameter node

        # If we are not ready to run, disable both buttons and turn off realTimeUpdates
        if not self._checkInputsValid():
            self.ui.applyButton.enabled = False
            self.ui.select_realTimeUpdate.setChecked(False)
            self.ui.select_realTimeUpdate.enabled = False
            
        # If we are ready to run,
        else:

            # And if realTimeUpdate is checked, keep the realTimeUpdate button enabled but disable the apply button
            if self.ui.select_realTimeUpdate.checked:
                self.ui.select_realTimeUpdate.enabled = True
                self.ui.applyButton.enabled = False

            # If realTimeUpdate is not checked, enable both buttons
            else:
                self.ui.applyButton.enabled = True
                self.ui.select_realTimeUpdate.enabled = True

        if self.ui.applyButton.enabled:
            self.ui.applyButton.toolTip = _("Compute AC-PC transformation")

    def _checkInputsValid(self) -> bool:
        """Check if the inputs are valid."""
        if not self._parameterNode.acpcLine:
            return False
        if not self._parameterNode.midlinePoints:
            return False
        return True

    def onCheckboxStateChanged(self, state: int) -> None:
        '''Executes when the checkbox state changes. I do not need to check to ensure that inputs are valid, because the checkbox
        is only enabled if the inputs are valid.'''
         # State is 2 when checkbox is checked, 0 when unchecked, and 1 when partially checked (is that possible with this kind of checkbox?)
         # If the checkbox is checked and I don't already have observers going, then start them
        if (state == 2) & (self.acpc_observer is None) & (self.midpoint_observer is None):
            self.acpc_observer = self.ui.select_acpcLine.currentNode().AddObserver(slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, lambda caller, event: self.onApplyButton())
            self.midpoint_observer = self.ui.select_midlinePoints.currentNode().AddObserver(slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, lambda caller, event: self.onApplyButton())
            self.onApplyButton()
        # If the checkbox is unchecked, remove observers
        elif state == 0:
            self.ui.select_acpcLine.currentNode().RemoveObserver(self.acpc_observer)
            self.ui.select_midlinePoints.currentNode().RemoveObserver(self.midpoint_observer)
            self.acpc_observer = None
            self.midpoint_observer = None

    def onApplyButton(self) -> None:
        """Run processing when user clicks "Apply" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            # Compute output
            self.logic.process(self.ui.select_acpcLine.currentNode(),
                               self.ui.select_midlinePoints.currentNode(),
                               self.ui.select_outputTransform.currentNode(),
                               self.ui.select_centerOn.currentText,
                               self.ui.select_folderNode.currentNode())
        
        
#
# ACPCLogic
#


class ACPCLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)

        # Doing this here because for some reason vtkMRMLMarkupsLineNode is not importable on Slicer startup
        # Hacky work-around, but it seems to work
        from slicer import vtkMRMLScalarVolumeNode, vtkMRMLMarkupsLineNode, vtkMRMLMarkupsFiducialNode, vtkMRMLLinearTransformNode, vtkMRMLMarkupsPlaneNode, vtkMRMLFolderDisplayNode

        @parameterNodeWrapper
        class inner_ACPCParameterNode:
            """
            The parameters needed by module.

            targetingVolume - The volume to transform.
            acpcLine - A line that goes from the anterior commissure to the posterior commissure.
            midlinePoint - A midline point(s)
            """
            outputTransform: vtkMRMLLinearTransformNode
            acpcLine: vtkMRMLMarkupsLineNode
            midlinePoints: vtkMRMLMarkupsFiducialNode
            #centerOn: str = WithinRange("MC", ["MC", "AC", "PC"])
            folderNode: vtkMRMLFolderDisplayNode
            #TODO: Make midlinePoints into a plane rather than fiducial nodes

        self.ACPCParameterNode = inner_ACPCParameterNode
        
    def getParameterNode(self):
        return self.ACPCParameterNode(super().getParameterNode())
    
    def process(self,
                acpcLine,
                midlinePoints,
                outputTransform,
                centerOn,
                folderNode) -> None:
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param targetingVolume: volume to be transformed
        :param acpcLine: the ACPC line
        :param midpoint: a midline plane
        """

        print(folderNode)

        if not acpcLine or not midlinePoints:
            raise ValueError("You must provide both an AC-PC line and a midline plane.")

        # The coordinates are in RAS space. The PC is the one that is more posterior.
        ac, pc = self.get_acpc_points(acpcLine)
        
        # Get an IH point, which is any point on the midline plane that is not along the AC-PC line.
        ih = midlinePoints.GetNthControlPointPosition(0)

        # Generate the transformation
        transform = self.get_acpc_transformation(ac, pc, ih, centerOn)
        outputTransform.SetMatrixTransformToParent(transform)

        # Apply the transformation on the ACPC line and midline points
        acpcLine.SetAndObserveTransformNodeID(outputTransform.GetID())
        midlinePoints.SetAndObserveTransformNodeID(outputTransform.GetID())

        # Apply the transformation on the foreground and background volumes of the red view
        red_composite = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceCompositeNodeRed')
        try:
            foregroundVolume = slicer.mrmlScene.GetNodeByID(red_composite.GetForegroundVolumeID())
            foregroundVolume.SetAndObserveTransformNodeID(outputTransform.GetID())
        except:
            pass    
        try:
            backgroundVolume = slicer.mrmlScene.GetNodeByID(red_composite.GetBackgroundVolumeID())
            backgroundVolume.SetAndObserveTransformNodeID(outputTransform.GetID())
        except:
            pass

        # If a folder node is provided, apply the transformation to all nodes in the folder
        if folderNode:

            # First, get the Subject Hierarchy
            shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
            folderID = shNode.GetItemByDataNode(folderNode)

            # Get all child items of the specified folder and store them in childItemIDs
            childItemIDs = vtk.vtkIdList()  # Creates an empty vtkIdList to hold item IDs
            shNode.GetItemChildren(folderID, childItemIDs, True)

            # Iterate through each ID in vtkIdList
            for i in range(childItemIDs.GetNumberOfIds()):
                itemID = childItemIDs.GetId(i)  # Get each ID
                associatedNode = shNode.GetItemDataNode(itemID)

                # If it's a transformable node, apply the transform
                if associatedNode and associatedNode.IsA("vtkMRMLTransformableNode"):
                    associatedNode.SetAndObserveTransformNodeID(outputTransform.GetID())
                
        # Ensure the slice views get reset to canonical Axial, Sagittal, Coronal, etc.
        slicer.app.layoutManager().sliceWidget("Red").setSliceOrientation("Axial")
        slicer.app.layoutManager().sliceWidget("Green").setSliceOrientation("Coronal")
        slicer.app.layoutManager().sliceWidget("Yellow").setSliceOrientation("Sagittal")

    def get_acpc_points(self, acpcLine):
        '''Anterior point is the AC, posterior point is the PC'''
        if acpcLine.GetLineStartPosition()[1] > acpcLine.GetLineEndPosition()[1]:
            ac = acpcLine.GetLineStartPosition()
            pc = acpcLine.GetLineEndPosition()
        else:
            ac = acpcLine.GetLineEndPosition()
            pc = acpcLine.GetLineStartPosition()
        return np.array([*ac]), np.array([*pc])
    
    def get_acpc_transformation(self, ac, pc, ih, center_on="MC"):
        # Y axis
        pcAc = ac - pc
        yAxis = pcAc / np.linalg.norm(pcAc)
        # X axis
        acIhDir = np.abs(ih - ac)
        xAxis = np.cross(yAxis, acIhDir)
        xAxis /= np.linalg.norm(xAxis)
        # Z axis
        zAxis = np.cross(xAxis, yAxis)
        # Rotation
        rotation = np.vstack([xAxis, yAxis, zAxis])

        if center_on == "MC":
            # Generate a translation that centers on the MC
            center_on = (ac + pc) / 2
        elif center_on == "AC":
            center_on = ac
        elif center_on == "PC":
            center_on = pc
        else:
            raise ValueError("center_on must be 'MC', 'AC', or 'PC'")
        translation = -np.dot(rotation, center_on)
        
        # Build matrix
        matrix = np.eye(4)
        matrix[:3, :3] = rotation
        matrix[:3, 3] = translation
        # Convert to VTK matrix
        matrix = slicer.util.vtkMatrixFromArray(matrix)
        return matrix



#
# ACPCTest
#


class ACPCTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_ACPC1()

    def test_ACPC1(self):
        """Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")
        # Test the module logic
        logic = ACPCLogic()

        # For now, the test is passed if the logic class is successfully instantiated
        self.delayDisplay("Test passed")


